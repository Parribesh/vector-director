"""Prompt -> one prop a stage can place: `vd prop "a stone well" --height-cm 110`.

The contract is what Sadhu's player expects of an object, and is checked in code, not
trusted from the model:

    viewBox 0 0 600 800, centre x=300, ground y=730, no background, ids that can't clash

The model draws in whatever coordinates it likes. A headless browser measures what it
drew, and code scales it to its real height and stands it on the ground line. Because
the size comes from `height_cm`, a well and a cup come out right next to a person.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError

from vector_director.m1_harness.llm import JsonLLM

SVGNS = "http://www.w3.org/2000/svg"
CANVAS = (600, 800)
CENTRE_X, GROUND_Y = 300, 730
# Sadhu's grown-up is 520 stage units tall at scale 1: call that 170 cm.
PX_PER_CM = 520 / 170
ALLOWED = {
    "g", "path", "rect", "circle", "ellipse", "polygon", "polyline", "line", "defs",
    "linearGradient", "radialGradient", "stop", "clipPath", "title", "desc",
}  # fmt: skip
URL_REF = re.compile(r"url\(#([^)]+)\)")

SYSTEM_PROMPT = """\
You draw one prop for a 2D animated Indian folk tale, as an SVG fragment.

Style: flat cartoon colours with a thick dark brown outline (#2A1A10, stroke-width about
1/60 of the prop's height), one lighter shade for the lit side and one darker for the shadow
side, simple readable shapes. Seen from the front, slightly from above. Warm earthy colours.

Draw only the thing itself. No background, no ground, no floor, no sky, no cast shadow, no
text, no people. Its bottom edge is where it meets the ground.
Use only: g, path, rect, circle, ellipse, polygon, polyline, line, and gradients in defs.
No style, script, image, use or text. Use any coordinates; it gets measured and scaled.
Aim for 10 to 60 shapes: enough to read at once, not a sketch.
"""


class PropDraft(BaseModel):
    svg: str = Field(description="The prop as an SVG fragment, without an outer <svg> element")


@dataclass
class Prop:
    slug: str
    svg: str
    png: bytes
    meta: dict = field(default_factory=dict)


def clean_fragment(fragment: str, prefix: str) -> str:
    """Parse, refuse anything but plain shapes, and prefix every id. Raises ValueError."""
    fragment = re.sub(r"<\?xml.*?\?>|<!--.*?-->", "", fragment, flags=re.DOTALL).strip()
    fragment = re.sub(r"^<svg\b[^>]*>|</svg>\s*$", "", fragment).strip()
    try:
        root = ET.fromstring(f'<g xmlns="{SVGNS}">{fragment}</g>')
    except ET.ParseError as e:
        raise ValueError(f"not well-formed XML: {e}") from e
    ids = {el.get("id") for el in root.iter() if el.get("id")}
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ALLOWED:
            raise ValueError(f"<{tag}> is not allowed")
        for name in list(el.attrib):
            if name.lower().startswith("on") or name.split("}")[-1] == "href":
                del el.attrib[name]
        if el.get("id"):
            el.set("id", f"{prefix}-{el.get('id')}")
        for name, value in el.attrib.items():
            el.set(
                name,
                URL_REF.sub(
                    lambda m: f"url(#{prefix}-{m.group(1)})" if m.group(1) in ids else "none", value
                ),
            )
    if not any(el.tag.split("}")[-1] not in ("g", "defs", "title", "desc") for el in root.iter()):
        raise ValueError("it draws nothing")
    ET.register_namespace("", SVGNS)
    return "".join(ET.tostring(child, encoding="unicode") for child in root)


def wrap(inner: str, transform: str = "") -> str:
    t = f' transform="{transform}"' if transform else ""
    return f'<svg xmlns="{SVGNS}" viewBox="0 0 {CANVAS[0]} {CANVAS[1]}"><g id="prop"{t}>{inner}</g></svg>'


def measure(page, inner: str) -> tuple[float, float, float, float]:
    """The drawing's bounding box, whatever coordinates it used."""
    page.set_content(
        f'<!doctype html><svg xmlns="{SVGNS}" width="10" height="10"><g id="prop">{inner}</g></svg>'
    )
    box = page.evaluate(
        "(() => { const b = document.getElementById('prop').getBBox(); return [b.x, b.y, b.width, b.height]; })()"
    )
    return tuple(box)


def place(inner: str, box: tuple[float, float, float, float], height_cm: float) -> str:
    """Scale to its real height, centre it, and stand it on the ground line."""
    x, y, w, h = box
    if w <= 0 or h <= 0:
        raise ValueError("it has no size")
    s = height_cm * PX_PER_CM / h
    tx, ty = CENTRE_X - (x + w / 2) * s, GROUND_Y - (y + h) * s
    return wrap(inner, f"translate({tx:.2f} {ty:.2f}) scale({s:.4f})")


def shoot(page, svg: str) -> tuple[bytes, dict]:
    """A transparent picture of the prop, and what it says about the contract."""
    from PIL import Image

    page.set_viewport_size({"width": CANVAS[0], "height": CANVAS[1]})
    page.set_content(
        f'<!doctype html><html style="background:transparent"><body style="margin:0;background:transparent">{svg}</body></html>'
    )
    png = page.screenshot(
        omit_background=True, clip={"x": 0, "y": 0, "width": CANVAS[0], "height": CANVAS[1]}
    )
    alpha = Image.open(io.BytesIO(png)).convert("RGBA").getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return png, {"coverage": 0.0, "bbox": None}
    left, top, right, bottom = bbox
    area = (right - left) * (bottom - top)
    solid = sum(1 for v in alpha.crop(bbox).getdata() if v > 128)
    return png, {"coverage": round(solid / area, 3), "bbox": list(bbox)}


def check(metrics: dict) -> list[str]:
    errors = []
    c = metrics["coverage"]
    if not metrics["bbox"]:
        errors.append("nothing visible was drawn")
    elif c > 0.97:
        errors.append(
            "it fills its whole box: it looks like a background or a plain rectangle, draw only the object"
        )
    elif c < 0.05:
        errors.append("it is almost empty: use filled shapes, not thin lines")
    return errors


def make_prop(
    prompt: str, slug: str, height_cm: float, llm: JsonLLM, page, repairs: int = 1
) -> Prop:
    ask = f"Draw: {prompt}\nIt is about {height_cm:g} cm tall in real life."
    tries: list[str] = []
    errors: list[str] = []
    bad = ""
    for attempt in range(repairs + 1):
        message = (
            ask
            if not errors
            else f"{ask}\n\nYour last try:\n{bad}\n\nFix these problems:\n"
            + "\n".join(f"- {e}" for e in errors)
        )
        reply = llm.ask(SYSTEM_PROMPT, message, PropDraft)
        try:
            bad = PropDraft.model_validate_json(reply.text).svg
            inner = clean_fragment(bad, slug)
            svg = place(inner, measure(page, inner), height_cm)
            png, metrics = shoot(page, svg)
            errors = check(metrics)
        except (ValidationError, ValueError) as e:
            errors, metrics, svg, png = [str(e)], {}, "", b""
        tries.append("; ".join(errors) or "ok")
        if not errors:
            return Prop(
                slug,
                svg,
                png,
                {
                    "prompt": prompt,
                    "height_cm": height_cm,
                    "provider": llm.provider,
                    "model": llm.model,
                    "attempts": attempt + 1,
                    "centre": [CENTRE_X, GROUND_Y],
                    **metrics,
                },
            )
    raise ValueError(f"{slug}: {' | '.join(tries)}")
