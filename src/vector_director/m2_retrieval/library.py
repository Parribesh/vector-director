"""The gallery: every prop and set piece, registered once, that any project can use.

    library/registry.json   one entry per item: what it is, its real size, where it came from
    library/items/<id>.svg  the art, on the stage contract (viewBox 0 0 600 800, centre x=300,
                            ground y=730) for props; a full 1200 x 800 stage for backdrops
    library/thumbs/<id>.png a picture of it, for CLIP and for Studio's gallery

`drawn_cm` is how tall the file is on a stage at scale 1, next to a grown-up 170 cm tall, and
`height_cm` the height it should be, so editing a size changes one number: a stage scales the
art by height_cm / drawn_cm.
"""

from __future__ import annotations

import colorsys
import io
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from vector_director.m1_harness.prop import PX_PER_CM, clean_fragment, measure, place

ASSET_UNITS_PER_CM = 3.7  # Sadhu's engine/asset-gen.js: about 370 units a metre
DEFAULT_ROOT = Path("library")
OPENMOJI_GROUPS = {"objects", "food-drink", "travel-places", "animals-nature"}
OPENMOJI_SKIP = re.compile(r"flag|symbol|sky-weather|transport-sign|clock|time|sound|money|mail|writing|science|medical|computer|phone|office|person|hand|face", re.IGNORECASE)
BAD_NUMBER = re.compile(r'<circle\b[^>]*\bc[xy]="[^"]*,[^"]*"[^>]*/>')  # older AI props have a few: a browser refuses them
GALLERY_COPY = re.compile(r"(sadhu|gen|openmoji)-")
OPENMOJI_LICENSE = "CC BY-SA 4.0, OpenMoji (openmoji.org)"


@dataclass
class Item:
    id: str
    name: str
    kind: str = "prop"  # prop | backdrop
    description: str = ""
    tags: list[str] = field(default_factory=list)
    height_cm: float = 100.0
    drawn_cm: float = 100.0
    source: str = ""
    license: str = ""
    status: str = "approved"  # approved | candidate
    palette: dict[str, str] = field(default_factory=dict)  # recolour with --c1, --c2... : see recolorable()

    def text(self) -> str:
        """What keyword search and CLIP's text side read."""
        return f"{self.name}. {' '.join(self.tags)}. {self.description}".strip()


class Registry:
    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.path = self.root / "registry.json"
        self.items: dict[str, Item] = {}
        if self.path.exists():
            self.items = {d["id"]: Item(**d) for d in json.loads(self.path.read_text())}

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        data = [asdict(i) for i in sorted(self.items.values(), key=lambda i: i.id)]
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")

    def svg_path(self, item_id: str) -> Path:
        return self.root / "items" / f"{item_id}.svg"

    def thumb_path(self, item_id: str) -> Path:
        return self.root / "thumbs" / f"{item_id}.png"

    def merged(self) -> dict[str, str]:
        """Items folded into another by `vd library tidy`, or refused (None): a re-seed leaves them out."""
        path = self.root / "merged.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def add(self, item: Item, svg: str) -> None:
        if item.id in self.merged():
            return
        if item.kind == "prop":
            svg, item.palette = recolorable(svg)
        self.svg_path(item.id).parent.mkdir(parents=True, exist_ok=True)
        self.svg_path(item.id).write_text(svg)
        self.items[item.id] = item

    def drop(self, item_id: str) -> None:
        del self.items[item_id]
        self.svg_path(item_id).unlink(missing_ok=True)
        self.thumb_path(item_id).unlink(missing_ok=True)

    def refuse(self, item_id: str) -> None:
        """Looked at and turned down: gone, and a re-seed leaves it out."""
        self.drop(item_id)
        path = self.root / "merged.json"
        path.write_text(json.dumps({**self.merged(), item_id: None}, indent=1))

    def update(self, item_id: str, **fields) -> Item:
        """An edit. Raises ValueError on anything that would break a stage."""
        item = self.items[item_id]
        if "height_cm" in fields and not (isinstance(fields["height_cm"], int | float) and fields["height_cm"] > 0):
            raise ValueError("height_cm must be a positive number")
        if "status" in fields and fields["status"] not in ("approved", "candidate"):
            raise ValueError("status is approved or candidate")
        if "tags" in fields and not (isinstance(fields["tags"], list) and all(isinstance(t, str) for t in fields["tags"])):
            raise ValueError("tags must be a list of words")
        for k in ("name", "description", "tags", "height_cm", "status"):
            if k in fields:
                setattr(item, k, fields[k])
        self.save()
        return item


COLOUR = re.compile(r'((?:fill|stroke|stop-color)(?:=")|(?:fill|stroke|stop-color):\s*)#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')


def _rgb(hex_colour: str) -> tuple[float, float, float]:
    h = hex_colour if len(hex_colour) == 6 else "".join(c * 2 for c in hex_colour)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _shade(rgb: tuple[float, ...], base: tuple[float, ...], n: int) -> str:
    """A shade of --c<n>, as a mix with black or white, whose fallback gives back exactly this colour."""
    to_hex = lambda c: "".join(f"{round(max(0.0, min(1.0, v)) * 255):02x}" for v in c)
    if max(rgb) <= max(base):
        p = max(max(rgb) / max(max(base), 1e-3), 0.01)
        return f"color-mix(in srgb,var(--c{n},#{to_hex(v / p for v in rgb)}) {p * 100:.1f}%,black)"
    p = max(min((1 - min(rgb)) / max(1 - min(base), 1e-3), 1.0), 0.01)
    return f"color-mix(in srgb,var(--c{n},#{to_hex((v - (1 - p)) / p for v in rgb)}) {p * 100:.1f}%,white)"


def recolorable(svg: str, groups: int = 3) -> tuple[str, dict[str, str]]:
    """Turns an item's main colours into CSS variables, so one drawing can be any colour: set --c1 on
    its group. Shades of a colour follow it (a mix with black or white), and with nothing set it looks
    exactly as it was drawn. Outlines and near-whites stay put."""
    counts: dict[str, int] = {}
    for _, value in COLOUR.findall(svg):
        counts[value.lower()] = counts.get(value.lower(), 0) + 1
    bases: list[dict] = []
    for value, _ in sorted(counts.items(), key=lambda kv: -kv[1]):
        h, l, sat = colorsys.rgb_to_hls(*_rgb(value))
        if l < 0.16 or l > 0.93:
            continue
        grey = sat < 0.12
        for b in bases:
            if b["grey"] == grey and (grey or min(abs(b["h"] - h), 1 - abs(b["h"] - h)) < 30 / 360):
                b["shades"][value] = l
                break
        else:
            if len(bases) < groups:
                bases.append({"hex": value, "h": h, "l": l, "grey": grey, "shades": {value: l}})
    swap: dict[str, str] = {}
    palette: dict[str, str] = {}
    for n, b in enumerate(bases, start=1):
        palette[f"c{n}"] = f"#{b['hex']}"
        base = _rgb(b["hex"])
        for value in b["shades"]:
            swap[value] = f"var(--c{n},#{b['hex']})" if value == b["hex"] else _shade(_rgb(value), base, n)
    return COLOUR.sub(lambda m: m.group(1) + swap.get(m.group(2).lower(), "#" + m.group(2)), svg), palette


def tidy(reg: Registry, vectors) -> dict[str, int]:
    """One item per kind. Pictures that are nearly the same become one, and Sadhu's variants of an asset
    (chair in wood, cane, plastic) become one for each view, since colour now does that job."""
    import numpy as np

    def family(item_id: str) -> tuple[str, float]:
        it = reg.items[item_id]
        if it.source.startswith("sadhu engine"):
            return f"asset:{it.tags[0]}:{item_id.split('-')[2] if len(item_id.split('-')) > 3 else ''}", 0.88
        return it.source.split()[0], 0.93

    merged, idx = reg.merged(), {i: k for k, i in enumerate(map(str, vectors.ids))}
    groups: dict[str, list[str]] = {}
    for i, it in reg.items.items():
        if it.kind == "prop" and i in idx:
            groups.setdefault(family(i)[0], []).append(i)
    rank = lambda i: (reg.items[i].status != "approved", not reg.items[i].description, reg.svg_path(i).stat().st_size)
    dropped = 0
    for members in groups.values():
        kept: list[str] = []
        for i in sorted(members, key=rank):
            near = next((k for k in kept if float(np.dot(vectors.image[idx[i]], vectors.image[idx[k]])) >= family(i)[1]), None)
            if near:
                merged[i] = near
                reg.drop(i)
                dropped += 1
            else:
                kept.append(i)
    (reg.root / "merged.json").write_text(json.dumps(merged, indent=0))
    recoloured = 0
    for i, it in reg.items.items():
        if it.kind == "prop" and not it.palette:
            svg, it.palette = recolorable(reg.svg_path(i).read_text())
            reg.svg_path(i).write_text(svg)
            recoloured += bool(it.palette)
    reg.save()
    return {"merged": dropped, "recoloured": recoloured, "left": len(reg.items)}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _bbox_px(page, svg: str) -> tuple[float, float, float, float]:
    page.set_viewport_size({"width": 1200, "height": 1000})
    page.set_content(f'<!doctype html><body style="margin:0">{svg}</body>')
    return tuple(page.evaluate(
        "(() => { const s = document.querySelector('svg'); const b = s.getBBox(); return [b.x, b.y, b.width, b.height]; })()"
    ))  # fmt: skip


def _drawn_height(page, svg: str, units_per_cm: float = PX_PER_CM) -> float:
    return round(_bbox_px(page, svg)[3] / units_per_cm, 1)


def seed_sadhu(reg: Registry, sadhu: Path, page, keep_edits: bool = True) -> dict[str, int]:
    """Sadhu's generated assets and hand-drawn objects as approved, its AI props as candidates."""
    counts = {"assets": 0, "objects": 0, "generated": 0, "backdrops": 0}

    def add(item: Item, svg: str) -> None:
        old = reg.items.get(item.id)
        if old and keep_edits:  # what you've edited survives a re-seed
            item.name, item.tags, item.height_cm, item.description, item.status = old.name, old.tags, old.height_cm, old.description, old.status
        reg.add(item, svg)

    out = subprocess.run(["node", "tools/export_assets.mjs"], cwd=sadhu, capture_output=True, text=True, check=True).stdout
    for a in json.loads(out):
        cm = _drawn_height(page, a["svg"], ASSET_UNITS_PER_CM)  # its size in the world it was drawn for
        words = [a["group"].lower(), a["view"], *([a["style"]] if a["style"] else [])]
        add(Item(id=f"sadhu-{a['id']}", name=a["label"], description=f"{a['label']}, {a['group'].lower()}, {a['view']} view", tags=[a["asset"], *words],
                 height_cm=cm, drawn_cm=_drawn_height(page, a["svg"]), source="sadhu engine/asset-gen.js", license="project"), a["svg"])
        counts["assets"] += 1
    for f in sorted((sadhu / "objects").glob("*.svg")):
        if GALLERY_COPY.match(f.stem):  # Studio copied it from here for a story
            continue
        svg = f.read_text()
        cm = _drawn_height(page, svg)
        add(Item(id=f"sadhu-{f.stem}", name=f.stem.replace("-", " "), tags=["sadhu", "object"], height_cm=cm, drawn_cm=cm, source=f"sadhu objects/{f.name}", license="project"), svg)
        counts["objects"] += 1
    for f in sorted((sadhu / "objects" / "generated").glob("*.svg")):
        meta = json.loads(f.with_suffix(".json").read_text()) if f.with_suffix(".json").exists() else {}
        cm = float(meta.get("height_cm", 100))
        add(Item(id=f"gen-{f.stem}", name=f.stem.replace("-", " "), description=meta.get("prompt", ""), tags=f.stem.split("-"), height_cm=cm, drawn_cm=cm,
                 source="vd prop", license="project", status="candidate"), BAD_NUMBER.sub("", f.read_text()))
        counts["generated"] += 1
    for f in sorted((sadhu / "sets").glob("*.svg")):
        if "--" in f.stem:  # a project's own export, not a set of its own
            continue
        add(Item(id=f"set-{f.stem}", name=f.stem.replace("-", " "), kind="backdrop", tags=["set", "backdrop", *f.stem.split("-")], height_cm=0, drawn_cm=0,
                 source=f"sadhu sets/{f.name}", license="project"), f.read_text())
        counts["backdrops"] += 1
    reg.save()
    return counts


def openmoji_entries(meta: list[dict]) -> list[dict]:
    """Single objects only: no flags, people, signs or skin-tone variants."""
    out = []
    for m in meta:
        if m.get("group") not in OPENMOJI_GROUPS or m.get("skintone") or OPENMOJI_SKIP.search(m.get("subgroups", "")):
            continue
        if m["annotation"].endswith("face"):  # a head alone: no use standing on a stage
            continue
        if "-" in m["hexcode"]:  # sequences: mostly variants of something already there
            continue
        out.append(m)
    return out


def seed_openmoji(reg: Registry, svg_dir: Path, meta: list[dict], page, heights: dict[str, float] | None = None) -> dict[str, int]:
    counts = {"added": 0, "refused": 0}
    for m in openmoji_entries(meta):
        f = svg_dir / f"{m['hexcode']}.svg"
        if not f.exists():
            continue
        item_id = f"openmoji-{slug(m['annotation'])}"
        cm = float((heights or {}).get(item_id, 60))
        try:
            inner = clean_fragment(f.read_text(), item_id)
            svg = place(inner, measure(page, inner), cm)
        except ValueError:
            counts["refused"] += 1
            continue
        old = reg.items.get(item_id)
        tags = [t.strip() for t in str(m.get("tags", "")).split(",") if t.strip()] + [m["group"], *m["subgroups"].split("-")]
        item = Item(id=item_id, name=m["annotation"], tags=tags, height_cm=old.height_cm if old else cm, drawn_cm=cm,
                    source="openmoji", license=OPENMOJI_LICENSE, status=old.status if old else "candidate")
        if old:
            item.tags, item.name = old.tags, old.name
        reg.add(item, svg)
        counts["added"] += 1
    reg.save()
    return counts


def make_thumbs(reg: Registry, page, only: list[str] | None = None, size: int = 256) -> int:
    """White background, cropped to the art, the way CLIP will see it."""
    from PIL import Image

    page.set_viewport_size({"width": size, "height": size})
    made = 0
    for item_id in reg.items if only is None else only:
        svg = reg.svg_path(item_id).read_text()
        page.set_content(f'<!doctype html><body style="margin:0;background:#fff"><div style="width:{size}px;height:{size}px">{svg}</div></body>')
        page.evaluate(
            """() => { const s = document.querySelector('svg'); const b = s.getBBox(); const m = Math.max(b.width, b.height) * 0.04;
                 if (!document.title && b.width && b.height) s.setAttribute('viewBox', `${b.x - m} ${b.y - m} ${b.width + 2 * m} ${b.height + 2 * m}`);
                 s.setAttribute('width', '100%'); s.setAttribute('height', '100%'); }"""
        )
        png = page.screenshot(clip={"x": 0, "y": 0, "width": size, "height": size})
        path = reg.thumb_path(item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.open(io.BytesIO(png)).convert("RGB").save(path)
        made += 1
    return made
