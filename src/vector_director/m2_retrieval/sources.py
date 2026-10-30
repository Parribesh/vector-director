"""Downloads for the gallery. Everything from outside is untrusted: it's parsed, cut down to plain
shapes and put on the stage contract before it can reach a browser or a story."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from vector_director.m1_harness.prop import ALLOWED, SVGNS, clean_fragment, measure, place
from vector_director.m2_retrieval.library import Item, Registry, slug

OPENCLIPART = "https://openclipart.org"
OPENCLIPART_LICENSE = "CC0 / public domain, Openclipart (openclipart.org)"
UA = {"User-Agent": "Mozilla/5.0 (sadhu-stories gallery builder)"}
MAX_BYTES = 400_000  # bigger files are traced photos or huge scenes, and slow the player

# What Indian folk tales keep needing, in Openclipart's words
QUERIES = """
market stall|market|bazaar|shop|storefront|vendor cart|awning|tent|canopy|warehouse|shed|barn|hut|cottage|village house
mud house|temple|hindu temple|shrine|palace|castle gate|fort|tower|lighthouse|stone wall|brick wall|wooden fence|gate|archway|bridge
pier|dock|jetty|fishing boat|sailboat|rowboat|ship|anchor|fishing net|net|rope|barrel|crate|sack|grain sack|basket|clay pot|jar|vase|amphora
well|water well|pump|bucket|fountain|lantern|oil lamp|torch|candle|campfire|fire pit|brazier|cauldron|anvil|scale balance|chest treasure
coin pile|scroll|book|sword|shield|spear|bow|axe|hammer|shovel|pickaxe|plough|wheelbarrow|ox cart|wagon|wheel|ladder|broom|stool|bench|table|bed
banyan|palm tree|coconut tree|neem|mango tree|oak tree|dead tree|bush|shrub|grass|flowers|lotus|rock|boulder|cliff|mountain|hill|sand dune|waterfall|pond|campfire logs|firewood|stump|log
cow|ox|goat|sheep|horse|elephant|camel|donkey|monkey|peacock|parrot|crow|dog|cat|rooster|chicken|snake|tiger|deer|fish
""".replace("\n", "|").strip("|").split("|")  # fmt: skip


def fetch(url: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read(MAX_BYTES + 1)


def openclipart_search(query: str, page: int = 1) -> list[tuple[str, str]]:
    html = fetch(f"{OPENCLIPART}/search/?{urllib.parse.urlencode({'query': query, 'p': page})}").decode("utf-8", "replace")
    return list(dict.fromkeys(re.findall(r"/detail/(\d+)/([a-z0-9-]+)", html)))


def download_openclipart(out: Path, per_query: int = 24, queries: list[str] = QUERIES, wait: float = 0.4) -> dict[str, int]:
    """Saves data/raw/openclipart/<id>.svg and an index of what each was found for."""
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    for q in queries:
        try:
            found = openclipart_search(q)[:per_query]
        except OSError as e:
            print(f"{q}: {e}", flush=True)
            continue
        new = 0
        for clip, name in found:
            if clip in index:
                if q not in index[clip]["queries"]:
                    index[clip]["queries"].append(q)
                continue
            try:
                data = fetch(f"{OPENCLIPART}/download/{clip}/{name}.svg")
            except OSError:
                continue
            if len(data) > MAX_BYTES or b"<svg" not in data[:4000]:
                continue
            (out / f"{clip}.svg").write_bytes(data)
            index[clip] = {"name": name, "queries": [q]}
            new += 1
            time.sleep(wait)
        print(f"{q}: {len(found)} found, {new} new", flush=True)
        index_path.write_text(json.dumps(index))
        time.sleep(wait)
    return {"downloaded": len(index)}


def _local(name: str) -> str:
    return name.split("}")[-1]


def to_fragment(svg: bytes | str) -> str:
    """An SVG from anywhere -> plain shapes clean_fragment accepts. Raises ValueError if it can't be."""
    text = svg.decode("utf-8", "replace") if isinstance(svg, bytes) else svg
    if "<!ENTITY" in text:
        raise ValueError("it declares XML entities")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"not well-formed: {e}") from e
    grads = {el.get("id"): el for el in root.iter() if _local(el.tag) in ("linearGradient", "radialGradient") and el.get("id")}

    def walk(el):
        for child in list(el):
            ns, tag = child.tag.split("}")[0].lstrip("{") if "}" in child.tag else SVGNS, _local(child.tag)
            if ns != SVGNS or tag in ("metadata", "title", "desc", "namedview", "filter", "sodipodi:namedview"):
                el.remove(child)
                continue
            if tag not in ALLOWED:
                raise ValueError(f"<{tag}> can't be used")
            walk(child)
        for name in list(el.attrib):
            if name.startswith("{") and not name.endswith("}href"):
                del el.attrib[name]
        if el.get("filter"):
            del el.attrib["filter"]
        if "filter:" in (el.get("style") or ""):
            el.set("style", re.sub(r"filter:[^;]*;?", "", el.get("style")))
        # a gradient that borrows its stops from another: copy them in, since links are dropped
        link = next((v for k, v in el.attrib.items() if k.endswith("href")), None)
        if link and link.startswith("#") and link[1:] in grads and not list(el):
            for stop in grads[link[1:]]:
                el.append(stop)

    walk(root)
    ET.register_namespace("", SVGNS)
    return "".join(ET.tostring(c, encoding="unicode") for c in root)


def seed_openclipart(reg: Registry, folder: Path, page) -> dict[str, int]:
    index = json.loads((folder / "index.json").read_text())
    counts = {"added": 0, "refused": 0}
    for clip, meta in index.items():
        item_id = f"oc-{slug(meta['name'])[:48]}-{clip}"
        try:
            inner = clean_fragment(to_fragment((folder / f"{clip}.svg").read_bytes()), item_id)
            svg = place(inner, measure(page, inner), 100)
        except (ValueError, OSError):
            counts["refused"] += 1
            continue
        old = reg.items.get(item_id)
        words = meta["name"].replace("-", " ")
        reg.add(Item(id=item_id, name=old.name if old else words, tags=old.tags if old else meta["queries"], height_cm=old.height_cm if old else 100, drawn_cm=100,
                     source=f"openclipart {OPENCLIPART}/detail/{clip}", license=OPENCLIPART_LICENSE, status=old.status if old else "candidate"), svg)  # fmt: skip
        counts["added"] += 1
    reg.save()
    return counts


LABEL_SYSTEM = """\
You sort clipart for a 2D cartoon of Indian folk tales. The sheet shows numbered pictures. For each number:
- keep: true only if it is ONE clear object, building, plant or animal that could stand on a stage: drawn in colour,
  flat or cartoon style. false for black-and-white line art, outlines, silhouettes, photos and photo-real art,
  logos, icons, symbols, text, maps, patterns, people, cartoons with faces on objects, groups of unrelated things,
  or anything modern (cars, phones, computers, modern city buildings).
- name: what it is, in 1 to 4 plain English words.
- description: one short sentence saying what it's made of and how it looks.
- height_cm: how tall the real thing stands.
Reply with every number on the sheet."""


def _sheet(reg: Registry, ids: list[str], cols: int = 6, cell: int = 200) -> bytes:
    import io

    from PIL import Image, ImageDraw

    rows = (len(ids) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), "white")
    draw = ImageDraw.Draw(sheet)
    for n, item_id in enumerate(ids):
        x, y = (n % cols) * cell, (n // cols) * cell
        sheet.paste(Image.open(reg.thumb_path(item_id)).convert("RGB").resize((cell - 8, cell - 8)), (x + 4, y + 4))
        draw.rectangle((x + 4, y + 4, x + 34, y + 22), fill="black")
        draw.text((x + 8, y + 7), str(n + 1), fill="white")
    out = io.BytesIO()
    sheet.save(out, "PNG")
    return out.getvalue()


def label_openclipart(reg: Registry, llm, per_sheet: int = 30) -> dict[str, int]:
    """Looks at every unlabelled download: keeps what suits the show, with a name, words and real size.
    The rest leave the gallery, and stay in data/raw if the rules change."""
    from concurrent.futures import ThreadPoolExecutor

    from pydantic import BaseModel

    class Label(BaseModel):
        number: int
        keep: bool
        name: str
        description: str
        height_cm: float

    class Sheet(BaseModel):
        items: list[Label]

    todo = [i for i, it in reg.items.items() if it.source.startswith("openclipart") and not it.description and reg.thumb_path(i).exists()]
    sheets = [todo[i : i + per_sheet] for i in range(0, len(todo), per_sheet)]

    def one(ids: list[str]):
        try:
            return ids, Sheet.model_validate_json(llm.ask(LABEL_SYSTEM, f"Label pictures 1 to {len(ids)}.", Sheet, images=[_sheet(reg, ids)], max_tokens=8000).text).items
        except Exception as e:  # noqa: BLE001
            print("sheet failed:", e, flush=True)
            return ids, []

    counts = {"kept": 0, "dropped": 0, "unread": 0}
    with ThreadPoolExecutor(6) as ex:
        for n, (ids, labels) in enumerate(ex.map(one, sheets), start=1):
            seen = {lab.number: lab for lab in labels}
            for k, item_id in enumerate(ids, start=1):
                lab = seen.get(k)
                if lab is None:
                    counts["unread"] += 1
                elif lab.keep and lab.height_cm > 0:
                    it = reg.items[item_id]
                    it.name, it.description, it.height_cm = lab.name, lab.description, lab.height_cm
                    counts["kept"] += 1
                else:
                    del reg.items[item_id]
                    reg.svg_path(item_id).unlink(missing_ok=True)
                    reg.thumb_path(item_id).unlink(missing_ok=True)
                    counts["dropped"] += 1
            reg.save()
            print(f"sheet {n}/{len(sheets)} {counts}", flush=True)
    return counts
