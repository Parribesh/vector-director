"""The director, from an idea to a production Studio can open and edit.

    1. story      (optional) a story written to a template's stages (sadhu/bible/templates/*.json), on its
                  own or as an episode of a series (sadhu/bible/series/<id>/)
    2. breakdown  the outline: each scene's place and time, who is present and what is needed. No design.
    3. casting    who has to be built and which places exist, one id each, checked in code against every
                  name in the outline; then a continuity pass, which may add people and places
    4. scene      one per scene: narration, lines and actions
    5. builders   one per new character, by kind: a person (body3d) or an animal (animal3d), each reading
                  its brief and what it does in the written scenes
    6. sets       one per scene, in story order: the first at a place picks its background and what stands
                  there; a return only says what changed. Each thing is searched in the gallery and
                  picked by id; what isn't there goes on the wanted list
    7. direct     one per scene: entrances, moves, poses and camera, once the sets exist
    8. accounting every name in the outline, and where it ended up

The model only ever picks from menus made from the engine's and gallery's own contents, so whatever
it answers can be drawn; code turns the picks into characters and sets and checks every id.
"""

from __future__ import annotations

import copy
import json
import math
import re
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vector_director.director import llm as LLM
from vector_director.director.setbuilder import (
    BACKGROUNDS,
    FAR,
    MARK_X,
    ROOM_ROW_Y,
    ROOMS,
    ROW_Y,
    background,
    scale_for,
)

LANGS = {
    "hi": "Hindi (Devanagari script; natural spoken Hindi like popular Hindi story videos, not formal or Sanskritised)",
    "en": "simple spoken English",
}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DEVANAGARI = re.compile("[ऀ-ॿ]")
S, B, N, I = {"type": "STRING"}, {"type": "BOOLEAN"}, {"type": "NUMBER"}, {"type": "INTEGER"}


def arr(items: dict) -> dict:
    return {"type": "ARRAY", "items": items}


def obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "OBJECT", "properties": properties, "required": required if required is not None else list(properties)}


def en(*values) -> dict:
    flat = [str(x) for v in values for x in (v if isinstance(v, list | tuple | dict) else [v])]
    return {"type": "STRING", "enum": flat}


class Engine:
    """Sadhu's engine, run headless: it knows what can be drawn."""

    def __init__(self, sadhu: Path | str) -> None:
        self.root = Path(sadhu).resolve()
        self.menus = self.call("menus")

    def call(self, op: str, **kw):
        r = subprocess.run(["node", "tools/engine_bridge.mjs"], cwd=self.root, input=json.dumps({"op": op, **kw}), capture_output=True, text=True, timeout=30, check=False)
        if r.returncode:
            raise RuntimeError(f"engine {op}: {r.stderr.strip()[-300:]}")
        return json.loads(r.stdout)

    def template(self, template_id: str) -> dict:
        return json.loads((self.root / "bible" / "templates" / f"{template_id}.json").read_text())

    def bible(self) -> str:
        return (self.root / "bible" / "sadhu.md").read_text()

    def series(self, series_id: str) -> dict:
        return json.loads((self.root / "bible" / "series" / series_id / "series.json").read_text())

    def episode_path(self, series_id: str, number: int) -> Path:
        return self.root / "bible" / "series" / series_id / f"ep{number:02d}.json"

    def projects(self) -> list[dict]:
        out = []
        for f in sorted((self.root / "projects").glob("*/project.json")):
            try:
                out.append(json.loads(f.read_text()))
            except ValueError:
                continue
        return out


def look_schema(m: dict) -> dict:
    o, colour = m["outfit"], en(m["palette"])
    return obj({
        "age": en("child", "young", "adult", "old"), "body": en("thin", "average", "heavy"), "height": en("short", "average", "tall"),
        "skin": en(m["skin"]), "expression": en("stern", "calm", "kind", "cheerful", "sly"),
        "hair": en(o["hair"]), "hairColor": en(m["hairColors"]), "bun": B,
        "beard": en("none", "stubble", "short", "long"), "mustache": en(m["mustaches"]), "beardColor": en(m["hairColors"]),
        "headwear": en(o["headwear"]), "headwearColor": colour,
        "top": en(o["top"]), "sleeves": B, "topColor": colour, "trimColor": en("none", m["palette"]),
        "bottom": en(o["bottom"]), "bottomColor": colour, "shoes": en("bare", "juti", "shoes"),
        "sash": B, "sashColor": colour, "janeu": B, "mala": B, "earrings": B, "wristBeads": B, "wrinkles": B, "swordBelt": B, "suit": B,
        "tilak": en(o["tilak"]), "blind": B, "holdRight": en(o["holdR"]), "holdLeft": en(o["holdL"]),
    })  # fmt: skip


SPOTS = ["wall-left", "wall-center", "wall-right", "back-left", "back-center", "back-right", "middle-left", "middle-right", "front-left", "front-right"]


def furniture_schema(m: dict) -> dict:
    return arr(obj({"asset": en(m["assets"]), "spot": en(SPOTS), "view": en("front", "three", "side"), "options": arr(S)}, ["asset", "spot"]))


def props_menu(m: dict) -> str:
    return "\n".join(
        f"- {k} ({a['label']}; views {'/'.join(a['views'])}): " + ", ".join(f"{o}={'|'.join(map(str, vals))}" for o, vals in a["options"])
        for k, a in m["assets"].items()
    )


def menus_3d(m: dict) -> dict:
    "The engine's menus, cut down to what the 3D catalog has."
    c = m["catalog3d"]
    return {**m, "assets": {k: v for k, v in m["assets"].items() if k in c["furniture"]}, "animals": {**m["animals"], "species": [a for a in m["animals"]["species"] if a in c["animals"]]}}


def catalog_text(m: dict) -> str:
    things = "\n".join(f"- {i['id']}: {i['about']}, {i['height_cm']} cm" for i in m["catalog3d"]["things"])
    return f"""

## The 3D things that exist
This story is in 3D, and only these exist. item: the id of the one below that is the same kind of object as the
thing you list. If none is that kind of object, item is "none": it goes on a wanted list, which is better than
showing the wrong thing. List everything the place needs, whether it exists or not.
{things}"""


def gallery_text(m: dict, three_d: bool = False) -> str:
    "What can exist in a story. A 3D project may only use what has been modelled."
    m = menus_3d(m) if three_d else m
    room_props = ", ".join(f"{k} ({a['label']})" for k, a in m["assets"].items())
    listing = lambda k: ", ".join(v for v in m["outfit"][k] if v != "none")
    return "\n".join([
        f"Animals that can be built: {', '.join(m['animals']['species'])}. Any other animal can only be a picture on the set.",
        f"Characters (one adaptable body, any age, build and colour): hair {listing('hair')}; headwear {listing('headwear')}; top reaching {listing('top')}, with or without sleeves; bottom {listing('bottom')}; beards; mustaches {', '.join(x for x in m['mustaches'] if x != 'none')}; tilak; mala, janeu, earrings, wrist beads, a shawl/sash, a sword at the waist; cloudy (blind) eyes; holding {listing('holdR')}.",
        "Not drawable yet: saris, dupattas or other women's clothing, vehicles held by hand, weapons other than the sword.",
        f"Rooms: walls {'/'.join(m['walls'])}, floors {'/'.join(m['floors'])}, and these props: {room_props}.",
        f"Outdoor places: a sky for each time of day and a background, one of: {', '.join(BACKGROUNDS)}.",
        "Things in a place: any solid object that stands on the ground (a well, a stall, a shrine, a boat, a tree) comes from the art gallery, so list it in the set's features.",
    ])  # fmt: skip


def load_library(engine: Engine, current: dict) -> dict:
    """Everything already built that a new story may reuse. Only what was built or locked counts,
    so untouched drafts don't change the planner's input (and its cache). A base story, the fixed
    stories we test on, only ever sees the presets, so nothing else can change its cached answers."""
    lib: dict = {"cast": {}, "sets": {}}
    for cid, body in engine.menus["presets"].items():
        lib["cast"][cid] = {"id": cid, "name": "Baba Chillanand" if cid == "baba" else cid, "about": f"{cid} (preset)", "body3d": body}
    if current.get("base"):
        return lib
    others = [p for p in engine.projects() if p.get("id") != current.get("id")]
    for p in [current, *others]:
        for c in p.get("cast", []):
            if (c.get("body3d") or c.get("animal3d")) and (c.get("built") or c.get("locked")):
                lib["cast"][c["id"]] = {"id": c["id"], "name": c["name"], "about": f"{c.get('role', '')}: {c.get('description', '')}"[:160], "look": c.get("look"),
                                        **{k: c[k] for k in ("body3d", "animal3d", "species", "herd", "kind") if c.get(k)}}  # fmt: skip
        for s in p.get("sets", []):
            if (s.get("room") or s.get("land") or s.get("art")) and (s.get("built") or s.get("locked")):
                lib["sets"][s["id"]] = {"id": s["id"], "name": s["name"], "kind": s.get("kind"), "about": (s.get("description") or "")[:160],
                                        **{k: s[k] for k in ("room", "land", "art", "dressing") if s.get(k)}}  # fmt: skip
    return lib


def library_text(lib: dict) -> str:
    return "\n".join(["Characters:", *(f"- {c['id']}: {c['name']}, {c['about']}" for c in lib["cast"].values()),
                      "Sets:", *(f"- {s['id']} ({s['kind']}): {s['name']}, {s['about']}" for s in lib["sets"].values())])  # fmt: skip


# ---------- checks (free) ----------
def check_plan(plan: dict, tpl: dict, lib: dict) -> list[str]:
    errors: list[str] = []
    cast_ids: set[str] = set()
    set_ids: set[str] = set()
    for c in plan["cast"]:
        if not SLUG.match(c["id"]):
            errors.append(f'cast id "{c["id"]}" must be a lowercase slug')
        if c["id"] in cast_ids:
            errors.append(f'cast id "{c["id"]}" is used twice')
        cast_ids.add(c["id"])
        if c.get("reuse") and c["reuse"] not in lib["cast"]:
            c["reuse"] = ""  # not in the library: design it fresh
    for s in plan["sets"]:
        if not SLUG.match(s["id"]):
            errors.append(f'set id "{s["id"]}" must be a lowercase slug')
        if s["id"] in set_ids:
            errors.append(f'set id "{s["id"]}" is used twice')
        set_ids.add(s["id"])
        if s.get("reuse") and s["reuse"] not in lib["sets"]:
            s["reuse"] = ""
    order = [st["id"] for st in tpl["stages"]]
    last = 0
    for n, sc in enumerate(plan["scenes"], start=1):
        if sc["set"] not in set_ids:
            errors.append(f'scene {n} uses set "{sc["set"]}", which is not in sets')
        errors += [f'scene {n} has "{w}" in its cast, who is not in cast' for w in sc["cast"] if w not in cast_ids]
        k = order.index(sc["stage"]) if sc["stage"] in order else -1
        if k < last:
            errors.append(f'scene {n} (stage "{sc["stage"]}") comes after a later stage: scenes must follow the stages in order')
        last = max(last, k)
    fewest = re.search(r"(\d+)-\d+ scenes", tpl.get("length", ""))
    if fewest and len(plan["scenes"]) < int(fewest.group(1)):
        errors.append(f"the plan has {len(plan['scenes'])} scenes but needs at least {fewest.group(1)}: split scenes by each change of place or time, and keep the story's events")
    for st in tpl["stages"]:
        scenes = [sc for sc in plan["scenes"] if sc["stage"] == st["id"]]
        if not scenes:
            errors.append(f'stage "{st["id"]}" has no scene')
        if st.get("baba") and not any("baba" in sc["cast"] for sc in scenes):
            errors.append(f'stage "{st["id"]}" needs Baba (id "baba") in a scene\'s cast')
    errors += [f'cast "{c["id"]}" is in no scene: add them to a scene\'s cast or remove them' for c in plan["cast"] if not any(c["id"] in sc["cast"] for sc in plan["scenes"])]
    errors += [f'set "{s["id"]}" is used by no scene: use it or remove it' for s in plan["sets"] if not any(sc["set"] == s["id"] for sc in plan["scenes"])]
    return errors


def check_breakdown(b: dict, tpl: dict) -> list[str]:
    errors: list[str] = []
    order, last = [st["id"] for st in tpl["stages"]], 0
    for n, sc in enumerate(b["scenes"], start=1):
        k = order.index(sc["stage"]) if sc["stage"] in order else -1
        if k < last:
            errors.append(f'scene {n} (stage "{sc["stage"]}") comes after a later stage: scenes must follow the stages in order')
        last = max(last, k)
        if not sc["present"]:
            errors.append(f"scene {n} has nobody present")
    fewest = re.search(r"(\d+)-\d+ scenes", tpl.get("length", ""))
    if fewest and len(b["scenes"]) < int(fewest.group(1)):
        errors.append(f"the outline has {len(b['scenes'])} scenes but needs at least {fewest.group(1)}: split scenes by each change of place or time, and keep the story's events")
    errors += [f'stage "{st["id"]}" has no scene' for st in tpl["stages"] if not any(sc["stage"] == st["id"] for sc in b["scenes"])]
    return errors


def name_key(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^the\s+", "", (name or "").strip().lower()))


def names_of(entry: dict) -> set[str]:
    return {name_key(n) for n in [entry.get("id"), entry.get("name"), *(entry.get("aka") or [])] if n}


def apply_casting(outline: dict, casting: dict, species: list[str]) -> tuple[dict, list[str]]:
    "The outline's names -> ids: a plan every later step can use, and every name that has no home."
    errors: list[str] = []
    animal_names = {name_key(p["name"]) for sc in outline["scenes"] for p in sc["present"] if p.get("what") == "animal"}
    # an animal cast as people (crows as a crowd) would be drawn as a person: it's a picture on the set
    strays = [c for c in casting["cast"] if c.get("kind") != "animal" and names_of(c) and names_of(c) <= animal_names]
    casting = {**casting, "cast": [c for c in casting["cast"] if c not in strays], "pictures": [*casting.get("pictures", []), *strays]}
    who = {n: c["id"] for c in casting["cast"] for n in names_of(c)}
    where = {n: s["id"] for s in casting["places"] for n in names_of(s)}
    pictures = {n: p["name"] for p in casting.get("pictures", []) for n in names_of(p)}
    left = {name_key(x["name"]): x["why"] for x in casting.get("leftOut", [])}
    held = {name_key(h["thing"]): h["who"] for h in casting.get("held", [])}
    ids = {c["id"] for c in casting["cast"]}
    for c in casting["cast"]:
        if c.get("kind") == "animal" and c.get("species") not in species:
            errors.append(f'"{c["id"]}": animal species must be one of {", ".join(species)}; any other animal goes in pictures')
    errors += [f'held: "{h["who"]}" is not a cast id' for h in casting.get("held", []) if h["who"] not in ids]
    scenes = []
    for n, sc in enumerate(outline["scenes"], start=1):
        cast, things, named = [], [], []
        for p in sc["present"]:
            key = name_key(p["name"])
            if key in who:
                cast.append(who[key])
                named.append({"name": p["name"], "kind": p.get("what", "person"), "id": who[key]})
            elif key in pictures:
                things.append(pictures[key])
                named.append({"name": pictures[key], "kind": "picture"})
            elif key in left:
                named.append({"name": p["name"], "kind": "left", "why": left[key]})
            else:
                errors.append(f'scene {n}: "{p["name"]}" is present, but in no cast entry\'s aka, no picture\'s aka and not in leftOut')
        for t in sc.get("things") or []:
            key = name_key(t)
            if key in held:
                named.append({"name": t, "kind": "held", "id": held[key]})
            else:
                things.append(t)
                named.append({"name": t, "kind": "thing"})
        place = where.get(name_key(sc["place"]))
        if not place:
            errors.append(f'scene {n}: place "{sc["place"]}" is in no place\'s aka')
        scenes.append({"stage": sc["stage"], "title": sc["title"], "set": place or "", "time": sc["time"], "cast": list(dict.fromkeys(cast)), "props": list(dict.fromkeys(things)),
                       "things": list(dict.fromkeys(things)), "named": named, "summary": sc["summary"], "mentioned": sc.get("mentioned") or []})  # fmt: skip
    plan = {"title": outline["title"], "logline": outline["logline"], "moral": outline["moral"], "cast": casting["cast"], "sets": casting["places"], "scenes": scenes,
            "held": casting.get("held", []), "missing": casting.get("missing") or []}  # fmt: skip
    return plan, errors


def account(scenes: list[dict], sets: list[dict], cast: list[dict], wanted: list[dict]) -> dict:
    "Every name in the outline and where it ended up, so that nothing disappears without a record."
    rows, wants = [], {name_key(w.get("for") or w.get("slug", "")) + f"@{w.get('scene', '')}" for w in wanted}
    by_id = {c["id"]: c for c in cast}
    for sc in scenes:
        st = next((s for s in sets if s["id"] == sc["set"]), {})
        here = {name_key(d.get("for", "")) for d in st.get("dressing", []) if d.get("for") and (not d.get("scenes") or sc["number"] in d["scenes"])}
        for n in sc.get("named", []):
            kind, status = n["kind"], "lost"
            if kind == "left":
                status = "left out"
            elif n.get("id") and kind != "held":
                status = "on screen" if n["id"] in sc["cast"] and n["id"] in by_id else "lost"
            elif kind == "held":
                body = by_id.get(n["id"], {}).get("body3d") or {}
                status = "held" if (body.get("outfit") or {}).get("holdR") or (body.get("outfit") or {}).get("holdL") else "wanted"
            elif name_key(n["name"]) in here:
                status = "on screen"
            elif name_key(n["name"]) + f"@{sc['number']}" in wants:
                status = "wanted"
            rows.append({"scene": sc["number"], "name": n["name"], "kind": kind, "status": status, **({"why": n["why"]} if n.get("why") else {})})
    count = {k: sum(r["status"] == k for r in rows) for k in ("on screen", "held", "wanted", "left out", "lost")}
    return {"total": len(rows), **count, "rows": rows}


def check_scene(out: dict, scene: dict, lang: str) -> list[str]:
    errors = []
    if len(out.get("beats") or []) < 3:
        errors.append("a scene needs at least 3 beats")
    for i, b in enumerate(out.get("beats") or [], start=1):
        if b["type"] == "narration":
            b["who"] = "narrator"
        elif b["who"] not in scene["cast"]:
            errors.append(f'beat {i}: "{b["who"]}" is not in this scene\'s cast ({", ".join(scene["cast"])})')
        if not (b.get("text") or "").strip():
            errors.append(f"beat {i} has no text")
        elif lang == "hi" and b["type"] != "action" and not DEVANAGARI.search(b["text"]):
            errors.append(f"beat {i} must be in Hindi (Devanagari script)")
        b["variant"] = "default"
    return errors


def pool(jobs: list[Callable], n: int = 4) -> list:
    with ThreadPoolExecutor(n) as ex:
        return [f.result() for f in [ex.submit(j) for j in jobs]]


class Run:
    """One job: its calls, its progress and what it cost."""

    def __init__(self, project_id: str, engine: Engine, gallery, on_step: Callable = lambda *a: None) -> None:
        self.project, self.engine, self.gallery, self.on_step = project_id, engine, gallery, on_step
        self.stats: dict = {"calls": 0, "cached": 0, "in": 0, "out": 0, "fallbacks": [], "failed": []}
        self.files: dict = {"sets": [], "objects": []}
        self.wanted: list[dict] = []
        self.three_d = False                                    # a 3D project: sets are dressed from the 3D catalog

    def ask(self, task: str, vars: dict, schema: dict, label: str, temperature: float = 0.7) -> dict:
        try:
            out = LLM.run(task, vars, schema, self.project, temperature)
        except LLM.LLMError as e:
            raise RuntimeError(f"{label}: {e}") from e
        self.stats["calls"] += 1
        if out["cached"]:
            self.stats["cached"] += 1
        else:
            self.stats["in"] += out["usage"].get("in", 0)
            self.stats["out"] += out["usage"].get("out", 0)
        if out["provider"] != "gemini" or out["tries"]:
            self.stats["fallbacks"].append(f"{label}: {out['provider']} {out['model']}")
        return out["data"]

    def checked(self, task: str, vars: dict, schema: dict, label: str, check: Callable, what: str) -> tuple[dict, list[str]]:
        """Ask, check in code, and repair once with the errors if the check fails."""
        data = self.ask(task, vars, schema, label)
        errors = check(data)
        if errors:
            self.on_step(label, "running", f"fixing {len(errors)} problem{'s' if len(errors) > 1 else ''}")
            data = self.ask("repair", {"what": what, "errors": "\n".join(f"- {e}" for e in errors), "context": "", "json": data}, schema, f"{label} (repair)")
            errors = check(data)
        return data, errors

    def step(self, label: str, fn: Callable) -> Callable:
        """A failure is reported on its step and leaves a default in place; the rest go on."""

        def job():
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                self.stats["failed"].append(label)
                self.on_step(label, "failed", str(e))

        return job


# ---------- the director proper: from a scene's beats to staging on its set ----------
STAGE_X = {"far-left": 170, "left": 340, "mid-left": 480, "centre": 600, "mid-right": 720, "right": 860, "far-right": 1030}
MARKS = {"off-left": {"x": -160, "y": 720}, "off-right": {"x": 1360, "y": 720},
         **{f"{r}-{c}": {"x": x, "y": y} for r, y in (("back", 680), ("front", 750)) for c, x in STAGE_X.items()}}  # fmt: skip
STAGE_POSES = ["stand", "namaste", "bless", "meditate"]
ANIMAL_POSES = ["stand", "alert", "graze", "sit", "lie"]
SITTING = re.compile("sit|sleep|meditate|lie")


def on_stage(p: dict) -> bool:
    return 0 < p["x"] < 1200


def dressing_in(st: dict | None, sc: dict) -> list[dict]:
    return [d for d in (st or {}).get("dressing", []) if not d.get("scenes") or sc["number"] in d["scenes"]]


def check_direction(d: dict, sc: dict, animals: set[str] | None = None) -> list[str]:
    errors, ids, where = [], set(sc["cast"]), {}
    animals = animals or set()
    wrong = lambda who, pose: pose not in (ANIMAL_POSES if who in animals else STAGE_POSES)
    errors += [f'start: "{s["who"]}" can\'t pose "{s["pose"]}"' for s in d["start"] if s.get("pose") and wrong(s["who"], s["pose"])]
    errors += [f'beat {i}: "{p["who"]}" can\'t pose "{p["pose"]}"' for i, b in enumerate(d["beats"], start=1) for p in b["poses"] if wrong(p["who"], p["pose"])]
    if len(d["beats"]) != len(sc["beats"]):
        errors.append(f"beats must have exactly {len(sc['beats'])} entries, it has {len(d['beats'])}")
    for s in d["start"]:
        if s["who"] not in ids:
            errors.append(f'start: "{s["who"]}" is not in the cast')
        where[s["who"]] = s["mark"]
    errors += [f'start: "{i}" has no mark' for i in ids if i not in where]
    for i, b in enumerate(d["beats"], start=1):
        for m in b["moves"]:
            if m["who"] not in ids:
                errors.append(f'beat {i}: "{m["who"]}" is not in the cast')
            where[m["who"]] = m["to"]
        errors += [f'beat {i}: "{p["who"]}" is not in the cast' for p in b["poses"] if p["who"] not in ids]
        beat = sc["beats"][i - 1] if i <= len(sc["beats"]) else None
        if beat and beat["type"] == "line" and where.get(beat["who"], "").startswith("off-"):
            errors.append(f"beat {i}: {beat['who']} speaks but is off stage")
        if b["shot"] not in ("keep", "wide") and b.get("on") not in ids:
            errors.append(f'beat {i}: a {b["shot"]} shot needs "on" to be someone in the cast')
    if len(sc["beats"]) > 3 and sum(b["shot"] != "keep" for b in d["beats"]) < 2:
        errors.append("the camera never changes: use at least two shots")
    return errors


def apply_direction(d: dict, sc: dict, st_set: dict | None, seats: dict, animals: set[str] | None = None) -> None:
    """The model's picks -> scene.staging.cast and beat.stage."""
    animals = animals or set()
    scale = 0.75 if (st_set or {}).get("room") else 0.8
    spots = {**MARKS, **seats}

    def free(mark: str, who: str, st: dict) -> dict:  # two people never share a mark
        m = spots.get(mark) or MARKS["back-centre"]
        at = {"x": m["x"], "y": m["y"]}
        if not on_stage(at):
            if who in animals:                                  # long, and maybe a herd: further out to be out of sight
                at["x"] = -800 if at["x"] < 0 else 2000
            return at
        wide = lambda o: 300 if who in animals or o in animals else 80     # an animal is long, so it needs more room
        taken = lambda x: any(o != who and abs(p["x"] - x) < wide(o) and abs(p["y"] - at["y"]) < 60 for o, p in st.items())
        for dx in (0, 90, -90, 180, -180, 270, -270, 360, -360, 450, -450, 540, -540):
            x = at["x"] + dx
            if 80 < x < 1120 and not taken(x):
                at["x"] = x
                break
        return at

    st: dict = {}
    for s in d["start"]:
        seat = seats.get(s["mark"])
        st[s["who"]] = {**free(s["mark"], s["who"], st), "scale": seat["scale"] if seat else scale, "turn": seat["turn"] if seat else 0,
                        "pose": seat["pose"] if seat else (s.get("pose") or "stand")}  # fmt: skip
    start = copy.deepcopy(st)
    for who in start:
        others = [o for o in st if o != who and on_stage(st[o])]
        if others and next(s for s in d["start"] if s["who"] == who)["mark"] not in seats:
            start[who]["turn"] = -1 if st[who]["x"] > 600 else 1
    sc["staging"] = {"cast": start}
    for who, p in st.items():
        p["turn"] = start[who]["turn"]
    seated = lambda p: any(v["x"] == p["x"] and v["y"] == p["y"] for v in seats.values())
    facing = lambda who, target: 1 if st[target]["x"] >= st[who]["x"] else -1
    last_shot = ""
    for i, beat in enumerate(sc["beats"]):
        b = d["beats"][i] if i < len(d["beats"]) else {"moves": [], "poses": [], "shot": "keep", "on": ""}
        stage: dict = {}
        for m in b["moves"]:
            who = m["who"]
            if who not in st:
                continue
            at, seat = free(m["to"], who, st), seats.get(m["to"])
            if math.hypot(at["x"] - st[who]["x"], at["y"] - st[who]["y"]) < 3:
                continue
            stage.setdefault("move", {})[who] = at
            st[who].update(at)
            pose = seat["pose"] if seat else "stand" if SITTING.search(st[who]["pose"]) else None
            if pose:
                stage.setdefault("pose", {})[who] = pose
                st[who]["pose"] = pose
        for p in b["poses"]:
            if p["who"] in st and st[p["who"]]["pose"] != p["pose"] and not seated(st[p["who"]]):
                stage.setdefault("pose", {})[p["who"]] = p["pose"]
                st[p["who"]]["pose"] = p["pose"]
        # on a line, the listeners face the speaker and the speaker faces the nearest listener
        if beat["type"] == "line" and beat["who"] in st:
            here = [o for o in st if on_stage(st[o]) and not SITTING.search(st[o]["pose"])]
            near = sorted((o for o in here if o != beat["who"]), key=lambda o: abs(st[o]["x"] - st[beat["who"]]["x"]))
            for who in here:
                turn = (facing(who, near[0]) if near else None) if who == beat["who"] else facing(who, beat["who"])
                if turn is not None and st[who]["turn"] != turn and who not in stage.get("move", {}):
                    stage.setdefault("turn", {})[who] = turn
                    st[who]["turn"] = turn
        shot = "" if b["shot"] == "keep" else "wide" if b["shot"] == "wide" else f"{b['shot']}:{b.get('on')}"
        if shot and shot != last_shot:
            stage["cam"] = {"shot": "wide"} if b["shot"] == "wide" else {"shot": b["shot"], "on": b["on"]}
            last_shot = shot
        if stage:
            beat["stage"] = stage
        else:
            beat.pop("stage", None)


def direct_scenes(run: Run, scenes: list[dict], sets: list[dict], cast: list[dict] | None = None) -> None:
    """Stage scenes on their sets, four at a time. A scene edited by hand stays as it was left."""
    animals = {c["id"] for c in cast or [] if c.get("animal3d")}

    def job(i: int, sc: dict):
        label = f"Direct {sc['number']}: {sc['title']}"
        st_set = next((s for s in sets if s["id"] == sc["set"]), None)
        seats = run.engine.call("seats", room=st_set["room"]) if st_set and st_set.get("room") else {}
        names = [*MARKS, *seats]
        schema = obj({"start": arr(obj({"who": en(sc["cast"]), "mark": en(names), "pose": en(dict.fromkeys(STAGE_POSES + ANIMAL_POSES))})),
                      "beats": arr(obj({"beat": I, "moves": arr(obj({"who": en(sc["cast"]), "to": en(names)})), "poses": arr(obj({"who": en(sc["cast"]), "pose": en(dict.fromkeys(STAGE_POSES + ANIMAL_POSES))})),
                                        "shot": en("keep", "wide", "medium", "close"), "on": S}))})  # fmt: skip
        run.on_step(label, "running")
        prev = scenes[i - 1] if i else None
        things = [{"name": d.get("need") or d["slug"], "at": "left" if d["x"] < 500 else "right" if d["x"] > 700 else "centre"} for d in dressing_in(st_set, sc)]
        data, errors = run.checked("direct", {
            "marks": ", ".join(names), "poses": ", ".join(STAGE_POSES), "animal_poses": ", ".join(ANIMAL_POSES), "animals": ", ".join(c for c in sc["cast"] if c in animals) or "none", "count": str(len(sc["beats"])),
            "set": json.dumps({"name": (st_set or {}).get("name"), "kind": (st_set or {}).get("kind"), "description": (st_set or {}).get("description"), "things": things}, ensure_ascii=False),
            "previous": f"{prev['summary']} (set: {prev['set']})" if prev else "none: this is the first scene",
            "scene": json.dumps({"title": sc["title"], "summary": sc["summary"], "cast": sc["cast"], "time": sc["time"],
                                 "beats": [{"beat": k + 1, "type": b["type"], "who": b.get("who"), "text": b["text"], "direction": b.get("direction")} for k, b in enumerate(sc["beats"])]}, ensure_ascii=False, indent=1),
        }, schema, label, lambda d: check_direction(d, sc, animals), f"the staging of one scene; its cast is {', '.join(sc['cast'])}, and it has {len(sc['beats'])} beats")  # fmt: skip
        apply_direction(data, sc, st_set, seats, animals)
        run.on_step(label, "warn" if errors else "done", "; ".join(errors))

    pool([run.step(f"Direct {sc['number']}: {sc['title']}", lambda i=i, sc=sc: job(i, sc)) for i, sc in enumerate(scenes) if not sc.get("locked") and sc.get("beats")])


# ---------- the set builder ----------
def usable(hit: dict) -> bool:
    return hit.get("source") != "openmoji" and hit.get("kind") == "prop" and hit.get("format", "svg") == "svg"  # emoji are for reference, not for a story's stage; a 2D story draws SVG


THING = {"slug": S, "for": S, "query": S, "prompt": S, "height_cm": N, "row": en("back", "front"), "mark": en(MARK_X)}


def free_mark(row: str, mark: str, standing: list[dict]) -> str | None:
    "The asked-for mark, or the nearest free one in that row. A room's spot such as front-left means its left."
    taken = {d["mark"] for d in standing if d["row"] == row}
    mark = mark if mark in MARK_X else {"center": "centre"}.get(mark.split("-")[-1], mark.split("-")[-1])
    mark = mark if mark in MARK_X else "centre"
    order = sorted(MARK_X, key=lambda m: abs(MARK_X[m] - MARK_X[mark]))
    return next((m for m in order if m not in taken), None)


def find_things(run: Run, st_set: dict, needs: list[dict], standing: list[dict], number: int, outdoors: bool) -> list[dict]:
    "Search the gallery for each need and pick by id; a need with no real match goes on the wanted list."
    if not needs:
        return []
    found = [[h for h in run.gallery.search(t["query"], k=20) if usable(h)][:8] for t in needs]
    text = "\n".join(
        f"- {t['slug']}: {t['prompt']} About {t['height_cm']} cm.\n" + "\n".join(f"  - {h['id']}: {h['name']}, {h['height_cm']} cm. {h['description']}" for h in hits)
        for t, hits in zip(needs, found, strict=True)
    )
    picks = {p["slug"]: p["id"] for p in run.ask("pick", {"needs": text}, obj({"picks": arr(obj({"slug": S, "id": S}))}), f"Pick: {st_set['name']}, scene {number}")["picks"]}
    rows, out = ROW_Y if outdoors else ROOM_ROW_Y, []
    for t, hits in zip(needs, found, strict=True):
        item = next((h for h in hits if h["id"] == picks.get(t["slug"]) and all(h["id"] != d["slug"] for d in standing + out)), None)
        mark = free_mark(t["row"], t["mark"], standing + out)
        if not item or not mark:
            run.wanted.append({"set": st_set["id"], "scene": number, "slug": t["slug"], "for": t.get("for", ""), "query": t["query"], "prompt": t["prompt"], "height_cm": t["height_cm"]})
            continue
        y = rows[t["row"]]
        run.files["objects"].append({"name": item["id"], "svg": run.gallery.reg.svg_path(item["id"]).read_text()})
        out.append({"slug": item["id"], "src": f"objects/{item['id']}.svg", "need": t["slug"], "for": t.get("for", ""), "x": MARK_X[mark], "y": y, "row": t["row"], "mark": mark,
                    "scale": scale_for(item, t["row"], st_set.get("kind", "outdoor"), y), "palette": item.get("palette") or {}, "scenes": []})  # fmt: skip
    return out


def find_things_3d(run: Run, st_set: dict, needs: list[dict], standing: list[dict], number: int, outdoors: bool) -> list[dict]:
    "The set builder already chose from the catalog; a need with no item, or no room left, goes on the wanted list."
    known, rows, out = {i["id"] for i in run.engine.menus["catalog3d"]["things"]}, ROW_Y if outdoors else ROOM_ROW_Y, []
    for t in needs:
        mark = free_mark(t["row"], t["mark"], standing + out)
        if t.get("item") not in known or not mark:
            run.wanted.append({"set": st_set["id"], "scene": number, "slug": t["slug"], "for": t.get("for", ""), "query": t["query"], "prompt": t["prompt"], "height_cm": t["height_cm"]})
            continue
        out.append({"slug": t["item"], "need": t["slug"], "for": t.get("for", ""), "x": MARK_X[mark], "y": rows[t["row"]], "row": t["row"], "mark": mark, "scenes": []})
    return out


def beats_text(sc: dict) -> str:
    return json.dumps({k: sc.get(k) for k in ("number", "time", "summary")} | {"actions": [b["text"] for b in sc.get("beats", []) if b.get("type") == "action"]}, ensure_ascii=False, indent=1)


def dress_set(run: Run, project_id: str, st_set: dict, scenes: list[dict]) -> None:
    """Build this place scene by scene, in story order: the first scene chooses the background and
    what stands there, each return says what changed, so a place keeps looking like itself. It's stored
    as one set whose items each list the scenes they're in. A need nobody placed goes on the wanted list."""
    outdoors, at = st_set.get("kind") != "interior", sorted((sc for sc in scenes if sc["set"] == st_set["id"]), key=lambda sc: sc["number"])
    about = json.dumps({k: st_set.get(k) for k in ("name", "kind", "description")}, ensure_ascii=False)
    standing: list[dict] = []
    three_d, menus = run.three_d, run.engine.menus
    thing = obj({**THING, "item": en("none", [i["id"] for i in menus["catalog3d"]["things"]])}) if three_d else obj(THING)
    catalog = catalog_text(menus) if three_d else ""
    backgrounds = {k: BACKGROUNDS[k] for k in menus["catalog3d"]["places"]} if three_d else BACKGROUNDS
    if st_set.get("reused"):                                   # a place from the library: this story only changes it
        for d in st_set.get("dressing", []):
            standing.append({**d, "need": d.get("need") or d["slug"], "for": d.get("for", ""), "row": d.get("row", "back"), "scenes": [], "mark": min(MARK_X, key=lambda m: abs(MARK_X[m] - d["x"]))})
    every: list[dict] = list(standing)
    for i, sc in enumerate(at):
        label = f"Set: {st_set['name']}, scene {sc['number']}"
        run.on_step(label, "running")
        required = sc.get("things") or sc.get("props") or []
        vars = {"set": about, "scene": beats_text(sc), "required": "\n".join(f"- {t}" for t in required) or "nothing in particular", "catalog": catalog}
        if i == 0 and not st_set.get("reused"):
            fields: dict = {"things": arr(thing)}
            if outdoors:
                fields["background"] = en(backgrounds)
                menu, extra = "\n".join(f"- {k}: {FAR[v[0]]}, {v[1]} ground" + (f", with a {v[2]} across it" if v[2] else "") for k, v in backgrounds.items()), ""
            elif st_set.get("room"):
                menu, extra = "This is a room that already has its walls, floor and furniture: only list what stands in it.", ""
            else:
                fields |= {"background": en(ROOMS), "furniture": furniture_schema(menus_3d(menus) if three_d else menus)}
                menu = "\n".join(f"- {k}: {v[0]} walls, a {v[1]} floor" for k, v in ROOMS.items())
                extra = ("- furniture: 4 to 9 pieces from this list, each at a spot: wall-left, wall-center, wall-right (hung on the back wall); back-left, back-center, back-right (against "
                         "it); middle-left, middle-right, front-left, front-right. Every seat a scene needs must be there. Options are key=value pairs from that piece's list.\n" + props_menu(menus_3d(menus) if three_d else menus))  # fmt: skip
            data = run.ask("set_first", {**vars, "backgrounds": menu, "furniture": extra}, obj(fields), label)
            if outdoors and three_d:
                st_set["background"] = data["background"]        # the 3D player builds the place itself
                st_set.pop("land", None)
            elif outdoors:
                name = f"{project_id}--{st_set['id']}"[:64]
                run.files["sets"].append({"name": name, "svg": background(data["background"], name)})
                st_set.update({"art": name, "background": data["background"]})
                st_set.pop("land", None)
            elif "furniture" in fields:
                light = next((t for t in ("night", "dusk") if t in (st_set.get("times") or [])), "day")
                wall, floor = ROOMS[data["background"]]
                st_set.update({"background": data["background"], "room": run.engine.call("room", layout={"wall": wall, "floor": floor, "light": light, "props": data["furniture"]})})
            needs = data["things"][:9]
        else:
            data = run.ask("set_return", {**vars, "standing": "\n".join(f"- {d['slug']}: {d['need']} ({d['row']} row, at {d['mark']})" for d in standing) or "nothing"},
                           obj({"remove": arr(S), "add": arr(thing)}), label)  # fmt: skip
            standing = [d for d in standing if d["slug"] not in data["remove"]]
            needs = data["add"][:5]
        new = (find_things_3d if three_d else find_things)(run, st_set, needs, standing, sc["number"], outdoors)
        standing += new
        every += new
        for d in standing:
            d["scenes"].append(sc["number"])
        placed = {name_key(d["for"]) for d in standing} | {name_key(w.get("for", "")) for w in run.wanted if w.get("scene") == sc["number"] and w.get("set") == st_set["id"]}
        for t in required:
            if name_key(t) not in placed:
                run.wanted.append({"set": st_set["id"], "scene": sc["number"], "slug": re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-"), "for": t, "query": t, "prompt": "The set builder didn't place this.", "height_cm": 0})
        run.on_step(label, "done", ", ".join(f"{d['need']}: {d['slug']}" for d in new) or "no change")
    numbers = [sc["number"] for sc in at]
    for d in every:
        d["scenes"] = [] if d["scenes"] == numbers else d["scenes"]    # in every scene here: an empty list says so
        d.pop("mark", None)
    st_set["dressing"] = sorted(every, key=lambda d: d["y"])  # the back row is drawn first


# ---------- the runner ----------
def cast_schema(species: list[str] | None = None) -> dict:
    return obj({"id": S, "name": S, "kind": en("person", "crowd", "animal"), "species": en("none", species or []), "herd": I, "role": S, "age": en("child", "young", "adult", "old"), "gender": en("male", "female", "average"), "build": en("thin", "average", "heavy"),
                "description": S, "personality": S, "look": obj({"skin": S, "hair": S, "facialHair": S, "clothing": S, "accessories": S}), "voice": S, "extra": B, "reuse": S, "aka": arr(S), "brief": S})  # fmt: skip


def animal_schema(m: dict, species: str) -> dict:
    return obj({"age": en("young", "adult", "old"), "size": en("small", "average", "big"), "coat": en(m["animals"]["coats"][species])})


def doing_in(cid: str, scenes: list[dict]) -> str:
    "What the written scenes have this one do and say."
    lines = [f"- scene {sc['number']}: {b['text']}" for sc in scenes if cid in sc["cast"] for b in sc.get("beats", []) if b.get("who") == cid and b.get("type") == "action"]
    return "\n".join(lines[:16]) or "Nothing in particular."


def break_down(run: Run, story: str, title: str, lang_text: str, tpl: dict) -> dict:
    on_step, times = run.on_step, run.engine.menus["times"]
    on_step("Breakdown", "running")
    outline_schema = obj({"title": S, "logline": S, "moral": S,
        "scenes": arr(obj({"stage": en([s["id"] for s in tpl["stages"]]), "title": S, "place": S, "time": en(times), "summary": S,
                           "present": arr(obj({"name": S, "what": en("person", "animal", "crowd")})), "things": arr(S), "mentioned": arr(S)}))})  # fmt: skip
    outline, errors = run.checked("breakdown", {
        "language": lang_text, "title": title, "story": story, "length": tpl["length"],
        "stages": "\n".join(f"- {s['id']} ({s['name']}{', Baba must appear' if s.get('baba') else ''}): {s['goal']}" for s in tpl["stages"]),
    }, outline_schema, "Breakdown", lambda b: check_breakdown(b, tpl), "the outline of an episode")  # fmt: skip
    if errors:
        on_step("Breakdown", "failed", "; ".join(errors))
        raise RuntimeError(f"The outline still has problems: {'; '.join(errors)}")
    on_step("Breakdown", "done", f"{len(outline['scenes'])} scenes")
    return outline


def run_pipeline(run: Run, project: dict, story: str, title: str, language: str = "hi", template_id: str = "baba-rescue") -> dict:
    engine, on_step = run.engine, run.on_step
    tpl, lib, lang_text, menus = engine.template(template_id), load_library(engine, project), LANGS.get(language, LANGS["hi"]), engine.menus
    run.three_d = project.get("mode") == "3d"
    times, species = menus["times"], (menus_3d(menus) if run.three_d else menus)["animals"]["species"]

    # the outline: what happens, where, and who and what is there
    outline = break_down(run, story, title, lang_text, tpl)

    # the cast and the places: one id each, and every name in the outline has a home
    on_step("Casting", "running")
    place_schema = obj({"id": S, "name": S, "kind": en("outdoor", "interior"), "description": S, "times": arr(en(times)), "reuse": S, "aka": arr(S)})
    casting_schema = obj({"cast": arr(cast_schema(species=species)), "pictures": arr(obj({"name": S, "aka": arr(S)})), "places": arr(place_schema),
                          "held": arr(obj({"who": S, "thing": S})), "leftOut": arr(obj({"name": S, "why": S})), "missing": arr(S)})  # fmt: skip

    def planned(c: dict) -> tuple[dict, list[str]]:
        p, errs = apply_casting(outline, c, species)
        for i, sc in enumerate(p["scenes"], start=1):            # numbered here: every later step goes by number
            sc["number"] = i
        return p, errs + (check_plan(p, tpl, lib) if not errs else [])

    casting, errors = run.checked("casting", {
        "language": lang_text, "species": ", ".join(species), "library": library_text(lib), "gallery": gallery_text(menus, run.three_d), "outline": json.dumps(outline["scenes"], ensure_ascii=False, indent=1),
    }, casting_schema, "Casting", lambda c: planned(c)[1], "the casting of an episode; every name in the outline's present lists and places must be in an aka, and these are the outline's scenes: " + json.dumps([{k: sc[k] for k in ("place", "present")} for sc in outline["scenes"]], ensure_ascii=False))  # fmt: skip
    if errors:
        on_step("Casting", "failed", "; ".join(errors))
        raise RuntimeError(f"The casting still has problems: {'; '.join(errors)}")
    plan = planned(casting)[0]
    for i, sc in enumerate(plan["scenes"], start=1):
        sc["number"], sc["id"] = i, f"s{i:02d}"
    on_step("Casting", "done", f"{len(plan['cast'])} in the cast, {sum(c.get('kind') == 'animal' for c in plan['cast'])} of them animals, {len(plan['sets'])} places")

    # the script supervisor: every scene in the right place, with the right people
    on_step("Continuity", "running")
    try:

        def revised(d: dict) -> dict:
            p = copy.deepcopy(plan)
            p["sets"] += d["newSets"]
            p["cast"] += d["newCast"]
            for c in d["scenes"]:
                sc = next((x for x in p["scenes"] if x["number"] == c["number"]), None)
                if sc:
                    added = [{"name": w, "kind": "added", "id": w} for w in c["cast"] if w not in sc["cast"]]
                    sc.update({k: c[k] for k in ("set", "cast", "time")})
                    sc["named"] = [*sc["named"], *added]
            p["sets"] = [s for s in p["sets"] if any(sc["set"] == s["id"] for sc in p["scenes"])]
            p["cast"] = [c for c in p["cast"] if any(c["id"] in sc["cast"] for sc in p["scenes"])]
            return p

        cont_schema = obj({"scenes": arr(obj({"number": I, "set": S, "cast": arr(S), "time": en(times), "why": S})), "newSets": arr(place_schema), "newCast": arr(cast_schema(species=species))})
        data, errors = run.checked("continuity", {"story": story, "gallery": gallery_text(menus, run.three_d), "plan": json.dumps({
            "cast": [{k: c[k] for k in ("id", "name", "role", "kind", "species")} for c in plan["cast"]],
            "sets": [{k: s[k] for k in ("id", "name", "kind", "description")} for s in plan["sets"]],
            "scenes": [{k: sc[k] for k in ("number", "title", "set", "time", "cast", "props", "summary")} for sc in plan["scenes"]]}, ensure_ascii=False, indent=1)},
            cont_schema, "Continuity", lambda d: check_plan(revised(d), tpl, lib), "a continuity check of a production plan; scenes may only use cast ids from the plan or newCast and set ids from the plan or newSets")  # fmt: skip
        if errors:
            on_step("Continuity", "warn", f"kept the plan as it was: {'; '.join(errors)}")
        else:
            p, changes = revised(data), [c for c in data["scenes"] if c.get("why") and c["why"] != "ok"]
            plan.update({k: p[k] for k in ("sets", "cast", "scenes")})
            on_step("Continuity", "done", f"{len(changes)} scene{'' if len(changes) == 1 else 's'} changed, {len(data['newCast'])} added to the cast, {len(data['newSets'])} new set{'' if len(data['newSets']) == 1 else 's'}")
    except Exception as e:  # noqa: BLE001
        run.stats["failed"].append("Continuity")
        on_step("Continuity", "failed", str(e))

    # the scene writers, all at once, all reading the same plan
    plan_text = json.dumps({"cast": [{k: c.get(k) for k in ("id", "name", "role", "kind", "voice")} for c in plan["cast"]],
                            "sets": [{k: s[k] for k in ("id", "name")} for s in plan["sets"]],
                            "scenes": [{k: sc[k] for k in ("number", "stage", "set", "time", "cast", "summary")} for sc in plan["scenes"]]}, ensure_ascii=False, indent=1)  # fmt: skip
    world = f"{plan['logline']}\nPlaces: {', '.join(s['name'] for s in plan['sets'])}"

    def scene(sc: dict):
        label = f"Scene {sc['number']}: {sc['title']}"
        sc["failed"] = True
        on_step(label, "running")
        schema = obj({"title": S, "summary": S, "beats": arr(obj({"type": en("narration", "line", "action"), "who": S, "text": S, "emotion": S, "direction": S}))})
        data, errors = run.checked("scene", {"language": lang_text, "story": story, "plan": plan_text, "scene": json.dumps({k: sc[k] for k in ("number", "stage", "title", "set", "time", "cast", "props", "summary")}, ensure_ascii=False, indent=1)}, schema, label,
                                   lambda d: check_scene(d, sc, language), f'one scene of an animated episode; only these cast ids may speak or act: {", ".join(sc["cast"])}; narration has who "narrator"')  # fmt: skip
        sc.update({"title": data.get("title") or sc["title"], "summary": data.get("summary") or sc["summary"], "beats": data["beats"]})
        if errors:
            sc["warnings"] = errors
        del sc["failed"]
        on_step(label, "warn" if errors else "done", "; ".join(errors))

    pool([run.step(f"Scene {sc['number']}: {sc['title']}", lambda sc=sc: scene(sc)) for sc in plan["scenes"]])
    for sc in plan["scenes"]:
        sc.setdefault("beats", [])

    # the character builders, by kind, each reading what its character does
    held = {c["id"]: [h["thing"] for h in plan.get("held", []) if h["who"] == c["id"]] for c in plan["cast"]}

    def character(c: dict):
        label = f"Character: {c['name']}"
        if c.get("reuse"):
            return on_step(label, "done", f"reused {c['reuse']}")
        c["failed"] = True  # until it's done: a re-run keeps the old one
        on_step(label, "running")
        doing = doing_in(c["id"], plan["scenes"]) + (f"\nCarries: {', '.join(held[c['id']])}" if held.get(c["id"]) else "")
        if c.get("kind") == "animal":
            look = run.ask("animal", {"character": json.dumps({k: c.get(k) for k in ("name", "species", "role", "description", "brief")}, ensure_ascii=False, indent=1), "doing": doing, "world": world}, animal_schema(menus, c["species"]), label)
            c["animal3d"] = engine.call("animal", look={**look, "species": c["species"], "herd": c.get("herd") or 1})
        else:
            others = "\n".join(f"- {o['name']}: {'; '.join(v for v in (o.get('look') or {}).values() if v)}" for o in plan["cast"] if o is not c and o.get("kind") != "animal")
            c["body3d"] = engine.call("body3d", look=run.ask("look", {"character": json.dumps(c, ensure_ascii=False, indent=1), "doing": doing, "others": others, "world": world}, look_schema(menus), label))
        del c["failed"]
        on_step(label, "done")

    pool([run.step(f"Character: {c['name']}", lambda c=c: character(c)) for c in plan["cast"]])

    # into the project's shapes
    cast = []
    for c in plan["cast"]:
        reused = lib["cast"].get(c.get("reuse") or "")
        base = {**{k: c.get(k) for k in ("id", "name", "role", "age", "gender", "build", "description", "personality", "look", "voice", "extra", "kind", "species", "herd", "brief")},
                "variants": [{"id": "default", "description": "", "design": {}}], "built": bool(reused), **({"failed": True} if c.get("failed") else {})}  # fmt: skip
        if c.get("kind") == "animal":
            cast.append({**base, "animal3d": copy.deepcopy(reused.get("animal3d")) if reused else c.get("animal3d") or engine.call("animal", look={"species": c.get("species"), "herd": c.get("herd") or 1})})
        else:
            body = copy.deepcopy(reused["body3d"]) if reused and reused.get("body3d") else c.get("body3d") or engine.call("defaultBody", age=c["age"], build=c["build"])
            cast.append({**base, "body3d": body, **({"draft": copy.deepcopy(c["body3d"])} if c.get("body3d") and not reused else {})})
    sets = []
    for s in plan["sets"]:
        reused = lib["sets"].get(s.get("reuse") or "")
        place = {k: copy.deepcopy(reused[k]) for k in ("room", "land", "art", "dressing") if reused.get(k)} if reused else {}
        sets.append({**{k: s.get(k) for k in ("id", "name", "kind", "description", "times")}, "features": [], **place, "built": False, **({"reused": True} if reused else {})})

    # build each place scene by scene, then stage every scene on its own
    pool([run.step(f"Set: {s['name']}", lambda s=s: dress_set(run, project["id"], s, plan["scenes"])) for s in sets if any(sc["set"] == s["id"] for sc in plan["scenes"])])
    direct_scenes(run, plan["scenes"], sets, cast)
    accounting = account(plan["scenes"], sets, cast, run.wanted)
    on_step("Accounting", "warn" if accounting["lost"] else "done", f"{accounting['total']} named: {accounting['on screen']} on screen, {accounting['held']} held, {accounting['wanted']} wanted, {accounting['left out']} left out, {accounting['lost']} lost")
    return {"title": plan["title"], "logline": plan["logline"], "moral": plan["moral"], "cast": cast, "sets": sets, "scenes": plan["scenes"],
            "missing": plan.get("missing") or [], "wanted": run.wanted, "accounting": accounting, "stats": run.stats, "files": run.files}  # fmt: skip


def story_schema(tpl: dict) -> dict:
    return obj({"title": S, "logline": S, "moral": S, "story": S, "stages": arr(obj({"stage": en([s["id"] for s in tpl["stages"]]), "summary": S}))})


def template_lines(tpl: dict) -> list[str]:
    return [tpl["description"], "", *(f"{s['id']}. {s['name']} ({s['scenes'][0]}-{s['scenes'][1]} scenes{', Baba appears' if s.get('baba') else ''}): {s['goal']}" for s in tpl["stages"]),
            "", "Rules:", *(f"- {x}" for x in tpl["rules"])]  # fmt: skip


def write_episode(run: Run, series_id: str, number: int, language: str = "hi") -> dict:
    """An episode of a series: the series and what came before -> a story -> its outline. Saved beside the series."""
    engine = run.engine
    series, path = engine.series(series_id), engine.episode_path(series_id, number)
    episode = series["episodes"][str(number)]
    tpl = engine.template(episode["template"])
    earlier = [engine.episode_path(series_id, n) for n in range(1, number)]
    previous = "\n".join(f"- Episode {n}: {json.loads(f.read_text())['logline']}" for n, f in enumerate(earlier, start=1) if f.exists()) or "None: this is the first."
    run.on_step("Story", "running")
    about = {k: series[k] for k in ("premise", "dimensions", "characters", "rules")}
    story = run.ask("episode", {"seriesName": series["name"], "number": str(number), "series": json.dumps(about, ensure_ascii=False, indent=1), "previous": previous, "brief": episode["brief"],
                                "templateName": tpl["name"], "template": "\n".join(template_lines(tpl)), "length": tpl["length"]}, story_schema(tpl), "Story", temperature=0.9)  # fmt: skip
    run.on_step("Story", "done", story["title"])
    outline = break_down(run, story["story"], story["title"], LANGS.get(language, LANGS["hi"]), tpl)
    out = {"series": series_id, "number": number, "template": tpl["id"], "language": language, **story, "outline": outline["scenes"], "stats": run.stats}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    from vector_director.director.film import write_project  # film.py builds on this module

    write_project(engine, series_id, number, out)
    return out


def write_story(run: Run, template_id: str, idea: str) -> dict:
    """A new story, written to the template."""
    tpl = run.engine.template(template_id)
    schema, lines = story_schema(tpl), template_lines(tpl)
    return run.ask("story", {"baba": run.engine.bible(), "templateName": tpl["name"], "idea": idea or "Your choice: a fresh, specific hero and problem from everyday Indian life.",
                             "length": tpl["length"], "template": "\n".join(lines)}, schema, "Story", temperature=0.9)  # fmt: skip
