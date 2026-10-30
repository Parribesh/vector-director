"""The director, from an idea to a production Studio can open and edit.

    1. story    (optional) a story written to a template's stages (sadhu/bible/templates/*.json)
    2. plan     the anchor: cast, sets and scenes with fixed ids, checked in code; then a continuity
                pass puts each scene in the right set with the right people
    3. at once: look   one per new character: menu picks -> a 3D character (body3d)
                room   one per indoor set: props at spots -> set.room
                scene  one per scene: narration, lines and actions
    4. dress    one per set: the far view, the ground and what stands there, each thing searched
                in the gallery and picked by id; what isn't there goes on the wanted list
    5. direct   one per scene: entrances, moves, poses and camera, once the sets exist

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
    FAR,
    GROUND,
    MARK_X,
    ROOM_ROW_Y,
    ROW_Y,
    backdrop,
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
        "sash": B, "sashColor": colour, "janeu": B, "mala": B, "earrings": B, "wristBeads": B, "wrinkles": B, "swordBelt": B,
        "tilak": en(o["tilak"]), "blind": B, "holdRight": en(o["holdR"]), "holdLeft": en(o["holdL"]),
    })  # fmt: skip


SPOTS = ["wall-left", "wall-center", "wall-right", "back-left", "back-center", "back-right", "middle-left", "middle-right", "front-left", "front-right"]


def room_schema(m: dict) -> dict:
    return obj({"wall": en(m["walls"]), "floor": en(m["floors"]), "light": en(m["lights"]),
                "props": arr(obj({"asset": en(m["assets"]), "spot": en(SPOTS), "view": en("front", "three", "side"), "options": arr(S)}, ["asset", "spot"]))})  # fmt: skip


def props_menu(m: dict) -> str:
    return "\n".join(
        f"- {k} ({a['label']}; views {'/'.join(a['views'])}): " + ", ".join(f"{o}={'|'.join(map(str, vals))}" for o, vals in a["options"])
        for k, a in m["assets"].items()
    )


def gallery_text(m: dict) -> str:
    room_props = ", ".join(f"{k} ({a['label']})" for k, a in m["assets"].items())
    listing = lambda k: ", ".join(v for v in m["outfit"][k] if v != "none")
    return "\n".join([
        f"Characters (one adaptable body, any age, build and colour): hair {listing('hair')}; headwear {listing('headwear')}; top reaching {listing('top')}, with or without sleeves; bottom {listing('bottom')}; beards; mustaches {', '.join(x for x in m['mustaches'] if x != 'none')}; tilak; mala, janeu, earrings, wrist beads, a shawl/sash, a sword at the waist; cloudy (blind) eyes; holding {listing('holdR')}.",
        "Not drawable yet: saris, dupattas or other women's clothing, vehicles held by hand, weapons other than the sword.",
        f"Rooms: walls {'/'.join(m['walls'])}, floors {'/'.join(m['floors'])}, and these props: {room_props}.",
        f"Outdoor places: a sky for each time of day, a far view ({', '.join(FAR)}) and a ground ({', '.join(GROUND)}).",
        "Things in a place: any solid object that stands on the ground (a well, a stall, a shrine, a boat, a tree) comes from the art gallery, so list it in the set's features.",
    ])  # fmt: skip


def load_library(engine: Engine, current: dict) -> dict:
    """Everything already built that a new story may reuse. Only what was built or locked counts,
    so untouched drafts don't change the planner's input (and its cache)."""
    lib: dict = {"cast": {}, "sets": {}}
    for cid, body in engine.menus["presets"].items():
        lib["cast"][cid] = {"id": cid, "name": "Baba Chillanand" if cid == "baba" else cid, "about": f"{cid} (preset)", "body3d": body}
    others = [p for p in engine.projects() if p.get("id") != current.get("id")]
    for p in [current, *others]:
        for c in p.get("cast", []):
            if c.get("body3d") and (c.get("built") or c.get("locked")):
                lib["cast"][c["id"]] = {"id": c["id"], "name": c["name"], "about": f"{c.get('role', '')}: {c.get('description', '')}"[:160], "body3d": c["body3d"], "look": c.get("look")}
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
SITTING = re.compile("sit|sleep|meditate")


def on_stage(p: dict) -> bool:
    return 0 < p["x"] < 1200


def dressing_in(st: dict | None, sc: dict) -> list[dict]:
    return [d for d in (st or {}).get("dressing", []) if not d.get("scenes") or sc["number"] in d["scenes"]]


def check_direction(d: dict, sc: dict) -> list[str]:
    errors, ids, where = [], set(sc["cast"]), {}
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


def apply_direction(d: dict, sc: dict, st_set: dict | None, seats: dict) -> None:
    """The model's picks -> scene.staging.cast and beat.stage."""
    scale = 0.75 if (st_set or {}).get("room") else 0.8
    spots = {**MARKS, **seats}

    def free(mark: str, who: str, st: dict) -> dict:  # two people never share a mark
        m = spots.get(mark) or MARKS["back-centre"]
        at = {"x": m["x"], "y": m["y"]}
        if not on_stage(at):
            return at
        taken = lambda x: any(o != who and abs(p["x"] - x) < 80 and abs(p["y"] - at["y"]) < 40 for o, p in st.items())
        for dx in (0, 90, -90, 180, -180, 270, -270, 360, -360):
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


def direct_scenes(run: Run, scenes: list[dict], sets: list[dict]) -> None:
    """Stage scenes on their sets, four at a time. A scene edited by hand stays as it was left."""

    def job(i: int, sc: dict):
        label = f"Direct {sc['number']}: {sc['title']}"
        st_set = next((s for s in sets if s["id"] == sc["set"]), None)
        seats = run.engine.call("seats", room=st_set["room"]) if st_set and st_set.get("room") else {}
        names = [*MARKS, *seats]
        schema = obj({"start": arr(obj({"who": en(sc["cast"]), "mark": en(names), "pose": en(STAGE_POSES)})),
                      "beats": arr(obj({"beat": I, "moves": arr(obj({"who": en(sc["cast"]), "to": en(names)})), "poses": arr(obj({"who": en(sc["cast"]), "pose": en(STAGE_POSES)})),
                                        "shot": en("keep", "wide", "medium", "close"), "on": S}))})  # fmt: skip
        run.on_step(label, "running")
        prev = scenes[i - 1] if i else None
        things = [{"name": d.get("need") or d["slug"], "at": "left" if d["x"] < 500 else "right" if d["x"] > 700 else "centre"} for d in dressing_in(st_set, sc)]
        data, errors = run.checked("direct", {
            "marks": ", ".join(names), "poses": ", ".join(STAGE_POSES), "count": str(len(sc["beats"])),
            "set": json.dumps({"name": (st_set or {}).get("name"), "kind": (st_set or {}).get("kind"), "description": (st_set or {}).get("description"), "things": things}, ensure_ascii=False),
            "previous": f"{prev['summary']} (set: {prev['set']})" if prev else "none: this is the first scene",
            "scene": json.dumps({"title": sc["title"], "summary": sc["summary"], "cast": sc["cast"], "time": sc["time"],
                                 "beats": [{"beat": k + 1, "type": b["type"], "who": b.get("who"), "text": b["text"], "direction": b.get("direction")} for k, b in enumerate(sc["beats"])]}, ensure_ascii=False, indent=1),
        }, schema, label, lambda d: check_direction(d, sc), f"the staging of one scene; its cast is {', '.join(sc['cast'])}, and it has {len(sc['beats'])} beats")  # fmt: skip
        apply_direction(data, sc, st_set, seats)
        run.on_step(label, "warn" if errors else "done", "; ".join(errors))

    pool([run.step(f"Direct {sc['number']}: {sc['title']}", lambda i=i, sc=sc: job(i, sc)) for i, sc in enumerate(scenes) if not sc.get("locked") and sc.get("beats")])


# ---------- the set dresser ----------
def usable(hit: dict) -> bool:
    return hit.get("source") != "openmoji" and hit.get("kind") == "prop"  # emoji are for reference, not for a story's stage


def dress_set(run: Run, project_id: str, st_set: dict, scenes: list[dict]) -> None:
    """What this place looks like; each thing searched, then picked by id. A need with no real
    match stays out of the scene and goes on the wanted list."""
    outdoors = st_set.get("kind") != "interior"
    label = f"Dress: {st_set['name']}"
    run.on_step(label, "running")
    fields: dict = {"things": arr(obj({"slug": S, "query": S, "prompt": S, "height_cm": N, "row": en("back", "front"), "mark": en(MARK_X), "scenes": arr(I)}))}
    if outdoors:
        fields |= {"far": en(FAR), "ground": en(GROUND)}
    at = [sc for sc in scenes if sc["set"] == st_set["id"]]
    data = run.ask("dress", {
        "set": json.dumps({k: st_set.get(k) for k in ("name", "kind", "description", "features")}, ensure_ascii=False),
        "far_note": "; ".join(f"{k}: {v}" for k, v in FAR.items()) if outdoors else "This is a room: use nothing.",
        "ground_note": ", ".join(GROUND) if outdoors else "This is a room: use nothing.",
        "drawn": ", ".join(i["asset"] for i in st_set["room"]["items"]) if st_set.get("room") else "only the sky, the far view and the ground",
        "scenes": "\n".join(f"- scene {sc['number']} ({sc['time']}): {sc['summary']} (props: {', '.join(sc.get('props') or []) or 'none'})" for sc in at),
    }, obj(fields), label)  # fmt: skip
    if outdoors:
        name = f"{project_id}--{st_set['id']}"[:64]
        run.files["sets"].append({"name": name, "svg": backdrop(data["far"], data["ground"], name)})
        st_set.update({"art": name, "far": data["far"], "ground": data["ground"]})
        st_set.pop("land", None)
    seen: set[tuple] = set()
    needs = [t for t in data["things"][:9] if (t["row"], t["mark"]) not in seen and not seen.add((t["row"], t["mark"]))]
    found = [[h for h in run.gallery.search(t["query"], k=20) if usable(h)][:8] for t in needs]
    text = "\n".join(
        f"- {t['slug']}: {t['prompt']} About {t['height_cm']} cm.\n" + "\n".join(f"  - {h['id']}: {h['name']}, {h['height_cm']} cm. {h['description']}" for h in hits)
        for t, hits in zip(needs, found, strict=True)
    )
    picks = {p["slug"]: p["id"] for p in run.ask("pick", {"needs": text}, obj({"picks": arr(obj({"slug": S, "id": S}))}), f"Pick: {st_set['name']}")["picks"]}
    rows = ROW_Y if outdoors else ROOM_ROW_Y
    dressing, chosen = [], set()
    for t, hits in zip(needs, found, strict=True):
        item = next((h for h in hits if h["id"] == picks.get(t["slug"]) and h["id"] not in chosen), None)
        if not item:
            run.wanted.append({"set": st_set["id"], "slug": t["slug"], "query": t["query"], "prompt": t["prompt"], "height_cm": t["height_cm"]})
            continue
        chosen.add(item["id"])
        y = rows[t["row"]]
        run.files["objects"].append({"name": item["id"], "svg": run.gallery.reg.svg_path(item["id"]).read_text()})
        dressing.append({"slug": item["id"], "src": f"objects/{item['id']}.svg", "need": t["slug"], "x": MARK_X[t["mark"]], "y": y, "row": t["row"],
                         "scale": scale_for(item, t["row"], st_set.get("kind", "outdoor"), y), "palette": item.get("palette") or {}, "scenes": t.get("scenes") or []})  # fmt: skip
    st_set["dressing"] = sorted(dressing, key=lambda d: d["y"])  # the back row is drawn first
    run.on_step(label, "done", ", ".join(f"{d['need']}: {d['slug']}" for d in st_set["dressing"]) + (f"; {len(needs) - len(dressing)} wanted" if len(dressing) < len(needs) else ""))


# ---------- the runner ----------
def run_pipeline(run: Run, project: dict, story: str, title: str, language: str = "hi", template_id: str = "baba-rescue") -> dict:
    engine, on_step = run.engine, run.on_step
    tpl, lib, lang_text, menus = engine.template(template_id), load_library(engine, project), LANGS.get(language, LANGS["hi"]), engine.menus
    times = menus["times"]

    # the plan: the anchor everything else follows
    on_step("Plan", "running")
    set_schema = obj({"id": S, "name": S, "kind": en("outdoor", "interior"), "description": S, "times": arr(en(times)), "features": arr(S), "reuse": S})
    plan_schema = obj({"title": S, "logline": S, "moral": S,
        "cast": arr(obj({"id": S, "name": S, "role": S, "age": en("child", "young", "adult", "old"), "gender": en("male", "female"), "build": en("thin", "average", "heavy"),
                         "description": S, "personality": S, "look": obj({"skin": S, "hair": S, "facialHair": S, "clothing": S, "accessories": S}), "voice": S, "extra": B, "reuse": S})),
        "sets": arr(set_schema),
        "scenes": arr(obj({"stage": en([s["id"] for s in tpl["stages"]]), "title": S, "set": S, "time": en(times), "cast": arr(S), "props": arr(S), "summary": S})),
        "missing": arr(S)})  # fmt: skip
    plan, errors = run.checked("plan", {
        "language": lang_text, "title": title, "story": story, "library": library_text(lib), "gallery": gallery_text(menus), "length": tpl["length"],
        "stages": "\n".join(f"- {s['id']} ({s['name']}{', Baba must appear' if s.get('baba') else ''}): {s['goal']}" for s in tpl["stages"]),
    }, plan_schema, "Plan", lambda p: check_plan(p, tpl, lib), "a production plan; scenes may only use the cast and set ids it lists")  # fmt: skip
    if errors:
        on_step("Plan", "failed", "; ".join(errors))
        raise RuntimeError(f"The plan still has problems: {'; '.join(errors)}")
    for i, sc in enumerate(plan["scenes"], start=1):
        sc["number"], sc["id"] = i, f"s{i:02d}"
    on_step("Plan", "done", f"{len(plan['cast'])} characters, {len(plan['sets'])} sets, {len(plan['scenes'])} scenes")

    # the script supervisor: every scene in the right place, with the right people
    on_step("Continuity", "running")
    try:

        def revised(d: dict) -> dict:
            p = copy.deepcopy(plan)
            p["sets"] += d["newSets"]
            for c in d["scenes"]:
                sc = next((x for x in p["scenes"] if x["number"] == c["number"]), None)
                if sc:
                    sc.update({k: c[k] for k in ("set", "cast", "time", "props")})
            p["sets"] = [s for s in p["sets"] if any(sc["set"] == s["id"] for sc in p["scenes"])]
            p["cast"] = [c for c in p["cast"] if any(c["id"] in sc["cast"] for sc in p["scenes"])]
            return p

        cont_schema = obj({"scenes": arr(obj({"number": I, "set": S, "cast": arr(S), "time": en(times), "props": arr(S), "why": S})), "newSets": arr(set_schema)})
        data, errors = run.checked("continuity", {"story": story, "gallery": gallery_text(menus), "plan": json.dumps({
            "cast": [{k: c[k] for k in ("id", "name", "role")} for c in plan["cast"]],
            "sets": [{k: s[k] for k in ("id", "name", "kind", "description")} for s in plan["sets"]],
            "scenes": [{k: sc[k] for k in ("number", "title", "set", "time", "cast", "props", "summary")} for sc in plan["scenes"]]}, ensure_ascii=False, indent=1)},
            cont_schema, "Continuity", lambda d: check_plan(revised(d), tpl, lib), "a continuity check of a production plan; scenes may only use cast ids from the plan and set ids from the plan or newSets")  # fmt: skip
        if errors:
            on_step("Continuity", "warn", f"kept the plan as it was: {'; '.join(errors)}")
        else:
            p, changes = revised(data), [c for c in data["scenes"] if c.get("why") and c["why"] != "ok"]
            plan.update({k: p[k] for k in ("sets", "cast", "scenes")})
            on_step("Continuity", "done", f"{len(changes)} scene{'' if len(changes) == 1 else 's'} changed, {len(data['newSets'])} new set{'' if len(data['newSets']) == 1 else 's'}")
    except Exception as e:  # noqa: BLE001
        run.stats["failed"].append("Continuity")
        on_step("Continuity", "failed", str(e))

    # designers and scene writers, all at once, all reading the same plan
    plan_text = json.dumps({"cast": [{k: c.get(k) for k in ("id", "name", "role", "voice")} for c in plan["cast"]],
                            "sets": [{k: s[k] for k in ("id", "name")} for s in plan["sets"]],
                            "scenes": [{k: sc[k] for k in ("number", "stage", "set", "time", "cast", "summary")} for sc in plan["scenes"]]}, ensure_ascii=False, indent=1)  # fmt: skip
    world = f"{plan['logline']}\nPlaces: {', '.join(s['name'] for s in plan['sets'])}"
    scenes_at = lambda sid: "\n".join(f"- {sc['time']}: {sc['summary']} (props: {', '.join(sc['props']) or 'none'})" for sc in plan["scenes"] if sc["set"] == sid)

    def character(c: dict):
        label = f"Character: {c['name']}"
        if c.get("reuse"):
            return on_step(label, "done", f"reused {c['reuse']}")
        c["failed"] = True  # until it's done: a re-run keeps the old one
        on_step(label, "running")
        others = "\n".join(f"- {o['name']}: {'; '.join((o.get('look') or {}).values())}" for o in plan["cast"] if o is not c)
        c["body3d"] = engine.call("body3d", look=run.ask("look", {"character": json.dumps(c, ensure_ascii=False, indent=1), "others": others, "world": world}, look_schema(menus), label))
        del c["failed"]
        on_step(label, "done")

    def room(s: dict):
        label = f"Set: {s['name']}"
        if s.get("reuse") or s["kind"] != "interior":
            return
        s["failed"] = True
        on_step(label, "running")
        layout = run.ask("room", {"set": json.dumps({k: s.get(k) for k in ("name", "kind", "description", "features", "times")}, ensure_ascii=False), "scenes": scenes_at(s["id"]), "props": props_menu(menus)}, room_schema(menus), label)
        s["room"] = engine.call("room", layout=layout)
        del s["failed"]
        on_step(label, "done")

    def scene(sc: dict):
        label = f"Scene {sc['number']}: {sc['title']}"
        sc["failed"] = True
        on_step(label, "running")
        schema = obj({"title": S, "summary": S, "beats": arr(obj({"type": en("narration", "line", "action"), "who": S, "text": S, "emotion": S, "direction": S}))})
        data, errors = run.checked("scene", {"language": lang_text, "story": story, "plan": plan_text, "scene": json.dumps(sc, ensure_ascii=False, indent=1)}, schema, label,
                                   lambda d: check_scene(d, sc, language), f'one scene of an animated episode; only these cast ids may speak or act: {", ".join(sc["cast"])}; narration has who "narrator"')  # fmt: skip
        sc.update({"title": data.get("title") or sc["title"], "summary": data.get("summary") or sc["summary"], "beats": data["beats"]})
        if errors:
            sc["warnings"] = errors
        del sc["failed"]
        on_step(label, "warn" if errors else "done", "; ".join(errors))

    pool([run.step(f"Character: {c['name']}", lambda c=c: character(c)) for c in plan["cast"]]
         + [run.step(f"Set: {s['name']}", lambda s=s: room(s)) for s in plan["sets"]]
         + [run.step(f"Scene {sc['number']}: {sc['title']}", lambda sc=sc: scene(sc)) for sc in plan["scenes"]])  # fmt: skip

    # into the project's shapes
    cast = []
    for c in plan["cast"]:
        reused = lib["cast"].get(c.get("reuse") or "")
        body = copy.deepcopy(reused["body3d"]) if reused else c.get("body3d") or engine.call("defaultBody", age=c["age"], build=c["build"])
        cast.append({**{k: c.get(k) for k in ("id", "name", "role", "age", "gender", "build", "description", "personality", "look", "voice", "extra")},
                     "variants": [{"id": "default", "description": "", "design": {}}], "body3d": body, "built": bool(reused),
                     **({"failed": True} if c.get("failed") else {}), **({"draft": copy.deepcopy(c["body3d"])} if c.get("body3d") and not reused else {})})  # fmt: skip
    sets = []
    for s in plan["sets"]:
        reused = lib["sets"].get(s.get("reuse") or "")
        place = {k: copy.deepcopy(reused[k]) for k in ("room", "land", "art", "dressing") if reused.get(k)} if reused else ({"room": s["room"]} if s.get("room") else {})
        sets.append({**{k: s.get(k) for k in ("id", "name", "kind", "description", "times", "features")}, **place, "built": False, **({"failed": True} if s.get("failed") else {}), **({"reused": True} if reused else {})})
    for sc in plan["scenes"]:
        sc.setdefault("beats", [])

    # build and dress the sets, then stage every scene on its own
    pool([run.step(f"Dress: {s['name']}", lambda s=s: dress_set(run, project["id"], s, plan["scenes"])) for s in sets if not s.get("reused") and not s.get("failed") and any(sc["set"] == s["id"] for sc in plan["scenes"])])
    direct_scenes(run, plan["scenes"], sets)
    return {"title": plan["title"], "logline": plan["logline"], "moral": plan["moral"], "cast": cast, "sets": sets, "scenes": plan["scenes"],
            "missing": plan.get("missing") or [], "wanted": run.wanted, "stats": run.stats, "files": run.files}  # fmt: skip


def write_story(run: Run, template_id: str, idea: str) -> dict:
    """A new story, written to the template."""
    tpl = run.engine.template(template_id)
    schema = obj({"title": S, "logline": S, "moral": S, "story": S, "stages": arr(obj({"stage": en([s["id"] for s in tpl["stages"]]), "summary": S}))})
    lines = [tpl["description"], "", *(f"{s['id']}. {s['name']} ({s['scenes'][0]}-{s['scenes'][1]} scenes{', Baba appears' if s.get('baba') else ''}): {s['goal']}" for s in tpl["stages"]),
             "", "Rules:", *(f"- {x}" for x in tpl["rules"])]  # fmt: skip
    return run.ask("story", {"baba": run.engine.bible(), "templateName": tpl["name"], "idea": idea or "Your choice: a fresh, specific hero and problem from everyday Indian life.",
                             "length": tpl["length"], "template": "\n".join(lines)}, schema, "Story", temperature=0.9)  # fmt: skip
