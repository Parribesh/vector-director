"""Prompt -> one place, drawn for this story: `vd set "a dry old stepwell" --slug stepwell`.

The model paints three layers on a 1200 x 800 stage: back, middle and ground. Code adds
what has to be right every time: the sky for each time of day, a tint for dusk and night
that follows the player's set-day / set-dusk / set-night classes, and the check that the
ground reaches the bottom of the stage, so people always have a floor under their feet.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from vector_director.m1_harness.llm import JsonLLM
from vector_director.m1_harness.prop import SVGNS, clean_fragment

W, H = 1200, 800
FLOOR_TOP = 620  # people stand from here down; the ground layer must fill it
SKIES = {
    "day": ("#7FB7E6", "#F3DFB4"),
    "dusk": ("#5A3C78", "#F0925A"),
    "night": ("#0B1436", "#2C3A66"),
}
TINT = {
    "outdoor": {"dusk": ("#C8642A", 0.2), "night": ("#0C1640", 0.5)},
    "interior": {"dusk": ("#A8582A", 0.14), "night": ("#1A1438", 0.34)},
}

SYSTEM_PROMPT = """\
You paint one location for a 2D animated Indian folk tale, as SVG fragments on a stage
1200 wide and 800 tall, origin top-left. This is a backdrop that people will act in front of.

Three layers, drawn in this order:
- back: the far distance. Outdoors: dunes, hills, a town's skyline, far trees, on top of a
  sky that is added for you, so leave the sky itself empty. Indoors: the whole back wall,
  from y=0 down, with its windows, niches and doors.
- middle: the big things that make this place itself: buildings, walls, arches, steps,
  terraces, the mouth of a well, standing against the back. Their bases sit between y=480
  and y=600. Paint the architecture here, specific to this place.
- ground: the floor. It must completely cover from its top edge (somewhere between y=470
  and y=600, not a straight line outdoors) down to y=800, from x=0 to x=1200, with a solid
  base shape first, then cracks, stones, tracks and tufts on top. Nothing tall here.

Keep the centre of the ground open: people walk there. No people, animals, text or
separate small objects: those are added later.

Style: flat cartoon colours, a thick dark brown outline (#2A1A10, stroke-width 3 to 5) on
the big shapes, a lighter shade for the lit side and a darker one for shadows, simple
readable shapes, warm earthy colours, clearly Indian. Draw for this exact place: it must
not look like any other place in the story.
Use only: g, path, rect, circle, ellipse, polygon, polyline, line, and gradients in defs.
No style, script, image, use or text. Aim for 60 to 200 shapes in all.
"""


class SetDraft(BaseModel):
    back: str
    middle: str
    ground: str


@dataclass
class SetArt:
    slug: str
    svg: str
    png: bytes
    meta: dict = field(default_factory=dict)


def compose(back: str, middle: str, ground: str, kind: str, slug: str) -> str:
    """The layers with the code's sky, time-of-day classes and tint."""
    tint = TINT.get(kind, TINT["outdoor"])
    css = "".join(f".set-{t} .{slug}-tint{{fill:{c};opacity:{o}}}" for t, (c, o) in tint.items())
    css += f".{slug}-sky{{display:none}}.set-day .{slug}-sky-day,.set-dusk .{slug}-sky-dusk,.set-night .{slug}-sky-night{{display:inline}}"
    grads = "".join(
        f'<linearGradient id="{slug}-g-{t}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient>'
        for t, (a, b) in SKIES.items()
    )
    skies = "".join(
        f'<rect class="{slug}-sky {slug}-sky-{t}" width="{W}" height="{H}" fill="url(#{slug}-g-{t})"/>'
        for t in SKIES
    )
    return (
        f'<svg xmlns="{SVGNS}" viewBox="0 0 {W} {H}"><defs>{grads}</defs><style>{css}</style>{skies}'
        f'<g id="{slug}-back">{back}</g><g id="{slug}-middle">{middle}</g><g id="{slug}-ground">{ground}</g>'
        f'<rect class="{slug}-tint" width="{W}" height="{H}" fill="none" opacity="0" pointer-events="none"/></svg>'
    )


def _layer(fragment: str, prefix: str, required: bool) -> str:
    if not fragment.strip() and not required:
        return ""
    return clean_fragment(fragment, prefix)


def check_ground(page, ground: str, slug: str) -> list[str]:
    """The floor must be solid everywhere people can stand."""
    from PIL import Image

    page.set_viewport_size({"width": W, "height": H})
    page.set_content(
        f'<!doctype html><html style="background:transparent"><body style="margin:0;background:transparent">'
        f'<svg xmlns="{SVGNS}" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{ground}</svg></body></html>'
    )
    png = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": W, "height": H})
    alpha = Image.open(io.BytesIO(png)).convert("RGBA").getchannel("A").crop((0, FLOOR_TOP, W, H))
    holes = sum(1 for v in alpha.getdata() if v < 200) / (W * (H - FLOOR_TOP))
    if holes > 0.01:
        return [
            f"the ground leaves {holes:.0%} of the floor empty below y={FLOOR_TOP}: start the ground layer with one solid shape reaching x=0, x=1200 and y=800"
        ]
    return []


def shoot_times(page, svg: str) -> bytes:
    """Day, dusk and night side by side, for looking at."""
    from PIL import Image

    sheet = Image.new("RGB", (W // 2 * 3, H // 2))
    page.set_viewport_size({"width": W, "height": H})
    for i, t in enumerate(SKIES):
        page.set_content(
            f'<!doctype html><body style="margin:0"><div class="set-{t}" style="width:{W}px;height:{H}px">{svg}</div></body>'
        )
        im = Image.open(io.BytesIO(page.screenshot())).convert("RGB").resize((W // 2, H // 2))
        sheet.paste(im, (i * W // 2, 0))
    out = io.BytesIO()
    sheet.save(out, "PNG")
    return out.getvalue()


def make_set(prompt: str, slug: str, kind: str, llm: JsonLLM, page, repairs: int = 1) -> SetArt:
    ask = f"Paint this {'indoor' if kind == 'interior' else 'outdoor'} location: {prompt}"
    tries: list[str] = []
    errors: list[str] = []
    for attempt in range(repairs + 1):
        message = (
            ask
            if not errors
            else f"{ask}\n\nYour last try had these problems, fix them:\n"
            + "\n".join(f"- {e}" for e in errors)
        )
        reply = llm.ask(SYSTEM_PROMPT, message, SetDraft, max_tokens=48000)
        try:
            d = SetDraft.model_validate_json(reply.text)
            back = _layer(d.back, slug, kind == "interior")
            middle = _layer(d.middle, f"{slug}-m", False)
            ground = _layer(d.ground, f"{slug}-g", True)
            errors = check_ground(page, ground, slug)
        except (ValidationError, ValueError) as e:
            errors = [str(e)]
        tries.append("; ".join(errors) or "ok")
        if not errors:
            svg = compose(back, middle, ground, kind, slug)
            return SetArt(
                slug,
                svg,
                shoot_times(page, svg),
                {
                    "prompt": prompt,
                    "kind": kind,
                    "provider": llm.provider,
                    "model": llm.model,
                    "attempts": attempt + 1,
                },
            )
    raise ValueError(f"{slug}: {' | '.join(tries)}")
