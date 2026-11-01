"""From an episode's outline to a film: each location planned and painted, each scene written and staged.

    1. sets    one call per location, then an image per layer. Saved under films/<id>/sets/<place>/, and a
               picture that's already there isn't painted again, so a rerun only pays for what changed.
    2. scenes  one call per scene, in story order, each reading the scene before: lines and staging together,
               because both are picks from what the set and the engine have.

The answer is checked in code, then turned into sadhu's film format (schemas/film.schema.json).
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import urllib.request
from pathlib import Path

from PIL import Image

from vector_director.director.pipeline import DEVANAGARI, LANGS, N, Run, S, arr, en, obj

IMAGE_MODEL = "gpt-image-1.5"
STYLE = "Simple flat-colour cartoon, like a modern 2D animated TV series: big clean shapes, few details, a limited palette, soft gradient shading only, thin dark ink outlines. It sits beside smooth, simple 3D cartoon characters. No text, no people."
FAR_RULE = "A background seen straight on from eye level. It fills the whole picture and repeats nothing important at the edges. The bottom edge of the picture is exactly where it meets the ground: show no floor or ground at all."
PIECE_RULE = "One object alone, seen exactly straight on from eye level, so its top surface isn't visible, on a fully transparent background. Nothing beneath it: no ground, floor, grass, rubble or shadow."
FLOOR_RULE = "A seamless repeating ground texture, seen straight down from above, with even flat light and no objects or shadows: "
OFF = {"off-left": (-8.0, 0.0), "off-right": (8.0, 0.0)}
POSES = ["stand", "talk", "excited", "angry", "serious", "pleading", "point", "think", "shrug", "scared", "crossed", "bless", "namaste"]
WALK_PACE = 1.05
VOICES = {
    "baba": {"say": {"voice": "Lekha", "rate": 150, "pitch": 0.72}, "gemini": {"voice": "Algenib", "note": "soft, low, amused old man"}},
    "cris": {"say": {"voice": "Lekha", "rate": 185, "pitch": 0.86}, "gemini": {"voice": "Puck", "note": "young man, quick, nervous, funny"}},
    "mira": {"say": {"voice": "Lekha", "rate": 170, "pitch": 1.0}, "gemini": {"voice": "Kore", "note": "calm, polite phone assistant"}},
    "evil": {"say": {"voice": "Lekha", "rate": 110, "pitch": 0.55}, "gemini": {"voice": "Charon", "note": "very deep, slow, cold, enjoying itself"}},
    "narrator": {"say": {"voice": "Lekha", "rate": 165, "pitch": 0.9}, "gemini": {"voice": "Iapetus", "note": "warm storyteller"}},
}
NAMES = {"baba": "बाबा", "cris": "क्रिस", "mira": "मीरा", "evil": "???", "narrator": ""}
ON_SCREEN = {"baba", "cris"}
HEARD = {"modern-life": ["mira"], "the-machine": ["mira"], "shadow": ["evil"]}      # only voices, and only where they can be heard


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def paint(path: Path, prompt: str, size: str, clear: bool = False) -> int:
    "Paints one layer, unless it's already there. -> how many images this paid for."
    if path.exists():
        return 0
    body = {"model": IMAGE_MODEL, "prompt": f"{prompt}\n\n{STYLE}", "size": size, "quality": "medium", "n": 1, **({"background": "transparent", "output_format": "png"} if clear else {})}
    req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=json.dumps(body).encode(), headers={"content-type": "application/json", "authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
    with urllib.request.urlopen(req, timeout=280) as r:
        raw = base64.b64decode(json.load(r)["data"][0]["b64_json"])
    tmp = path.with_suffix(".png.tmp")
    tmp.write_bytes(raw)
    img = Image.open(tmp)
    if clear:
        img = img.convert("RGBA")
        img = img.crop(img.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox())         # the object's own edges, so that its base stands on the ground
        img.save(path, quality=86, method=6)
    else:
        img.convert("RGB").save(path, quality=88)
    tmp.unlink()
    return 1


def build_place(run: Run, place: str, scenes: list[dict], folder: Path, only_plan: bool = False) -> tuple[dict, int]:
    folder.mkdir(parents=True, exist_ok=True)
    schema = obj({"backdrop": S, "floor": S, "light": en("warm", "cold", "neutral"), "portal_x": N, "portal_z": N,
                  "pieces": arr(obj({"name": S, "prompt": S, "height_m": N, "x": N, "z": N})), "marks": arr(obj({"name": S, "x": N, "z": N}))})  # fmt: skip
    about = {"place": place, "scenes": [{k: sc[k] for k in ("time", "summary", "things")} for sc in scenes]}
    plan = run.ask("set_layers", {"series": "Cris and Baba", "count": "3", "scene": json.dumps(about, ensure_ascii=False, indent=1)}, schema, f"Set: {place}")
    made = paint(folder / "backdrop.jpg", f"{plan['backdrop']}\n\n{FAR_RULE}", "1536x1024")
    made += paint(folder / "floor.jpg", FLOOR_RULE + plan["floor"], "1024x1024")
    for i, p in enumerate(plan["pieces"]):
        p["file"] = f"piece{i}.webp"
        made += paint(folder / p["file"], f"{p['prompt']}\n\n{PIECE_RULE}", "1024x1024", clear=True)
        with Image.open(folder / p["file"]) as img:
            p["aspect"] = round(img.width / img.height, 4)
    door = next((p for p in plan["pieces"] if re.search("arch|gate|door", p["name"], re.I)), None)     # a ring of light opens in a doorway, if the place has one
    portal = [door["x"], door["z"] + 0.05] if door else [plan["portal_x"], plan["portal_z"]]
    (folder / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n")
    return {"layers": True, "light": plan["light"], "pieces": plan["pieces"], "marks": plan["marks"], "portal": portal, "plan": {k: plan[k] for k in ("backdrop", "floor")}}, made


def check_scene(d: dict, here: list[str], marks: set[str], speakers: list[str]) -> list[str]:
    errors = []
    errors += [f'start: "{w}" has no mark' for w in here if not any(s["who"] == w for s in d["start"])]
    if not 2 <= len(d["shots"]) <= 6:
        errors.append("a scene has 2 to 6 shots")
    lines = 0
    for n, shot in enumerate(d["shots"], start=1):
        c = shot["camera"]
        if c in ("medium", "close", "over") and shot.get("on") not in here:
            errors.append(f'shot {n}: a {c} shot needs "on" to be someone on screen: {", ".join(here)}')
        if c in ("two", "over") and len(here) < 2:
            errors.append(f"shot {n}: {c} needs two people, and only {here[0]} is here")
        for b in shot["beats"]:
            if (b.get("say") or "").strip():
                lines += 1
                if b["who"] not in speakers:
                    errors.append(f'shot {n}: "{b["who"]}" can\'t speak here')
                if not DEVANAGARI.search(b["say"]):
                    errors.append(f"shot {n}: this line must be in Hindi (Devanagari script): {b['say'][:40]}")
                if b["walker"] != "none":
                    errors.append(f"shot {n}: a beat with a walk has say empty")
            if b["walker"] != "none" and (b["walker"] not in here or b["to"] not in marks):
                errors.append(f'shot {n}: a walk needs someone here and a mark, not "{b["walker"]}" to "{b["to"]}"')
    if lines < 3:
        errors.append("a scene needs at least 3 spoken lines")
    return errors


def to_shots(d: dict, number: int, set_name: str, spots: dict, here: list[str], where: dict) -> list[dict]:
    "The model's picks -> shots in the film format. `where` tracks where each person stands, so a walk knows how long it takes."
    shots = []
    start = {s["who"]: spots[s["mark"]] for s in d["start"] if s["who"] in here}
    where.update(start)
    start_pose = {s["who"]: s["pose"] for s in d["start"] if s["who"] in here}
    for k, shot in enumerate(d["shots"], start=1):
        camera = {"type": shot["camera"], **({"on": shot["on"]} if shot["camera"] in ("medium", "close", "over") else {}), **({"move": shot["move"]} if shot.get("move") in ("in", "out") else {})}
        beats = []
        for b in shot["beats"]:
            out: dict = {}
            if b["who"] != "nobody" and (b.get("say") or "").strip():
                out |= {"who": b["who"], "say": b["say"].strip()}
                if b["who"] in here and b["pose"] != "keep":
                    out["pose"] = b["pose"]
            if b["other_pose"] != "keep" and b["other"] in here:
                out["poses"] = {b["other"]: b["other_pose"]}
            if b["walker"] in here and b["to"] in spots:
                to = spots[b["to"]]
                out["walk"] = {b["walker"]: to}
                out["dur"] = round(math.dist(where[b["walker"]], to) / WALK_PACE + 0.5, 2)
                where[b["walker"]] = to
            if b["portal"] != "none":
                out["portal"] = {"open": {"dark": 0, "open": 1}, "rift": {"dark": 0.55, "open": 1}, "close": {"open": 0, "dark": 0}}[b["portal"]]
            if b["light"] != "none":
                out["dim"] = {"normal": 1, "dim": 0.55, "dark": 0.3}[b["light"]]
            if b["sound"] != "none":
                out["sound"] = b["sound"]
            if not out.get("say") and "dur" not in out:
                out["dur"] = 1.6
            beats.append(out)
        if k == 1:
            beats[0].setdefault("poses", {}).update({w: p for w, p in start_pose.items() if w not in beats[0].get("poses", {})})
        shots.append({"id": f"s{number:02d}{k}", "camera": camera, "beats": beats, **({"set": set_name, "place": start} if k == 1 else {})})
    return shots


def lines_of(shots: list[dict]) -> str:
    return "\n".join(f"{b['who']}: {b['say']}" for s in shots for b in s["beats"] if b.get("say"))


def write_scene(run: Run, ep: dict, series: dict, sc: dict, number: int, set_name: str, st: dict, previous: str, where: dict, language: str) -> list[dict]:
    here = [p for p in dict.fromkeys(slug(x["name"]) for x in sc["present"]) if p in ON_SCREEN]
    speakers = [*here, *HEARD.get(sc["stage"], []), "narrator"]
    spots = {**{m["name"]: [m["x"], m["z"]] for m in st["marks"]}, **{k: list(v) for k, v in OFF.items()}}
    pose = en("keep", POSES)
    schema = obj({"start": arr(obj({"who": en(here), "mark": en(spots), "pose": en(POSES)})),
                  "shots": arr(obj({"camera": en("wide", "two", "medium", "close", "over"), "on": S, "move": en("none", "in", "out"),
                                    "beats": arr(obj({"who": en("nobody", speakers), "say": S, "pose": pose, "other": S, "other_pose": pose, "walker": en("none", here), "to": en("none", spots),
                                                      "portal": en("none", "open", "rift", "close"), "light": en("none", "normal", "dim", "dark"), "sound": en("none", "wind-up", "wind-down", "rumble")}))}))})  # fmt: skip
    things = [{"name": p["name"], "x": p["x"], "z": p["z"]} for p in st["pieces"]]
    data, errors = run.checked("film_scene", {
        "series": series["name"], "about": json.dumps({k: series[k] for k in ("premise", "characters", "rules")}, ensure_ascii=False, indent=1), "story": ep["story"], "previous": previous,
        "set": json.dumps({"place": sc["place"], "things": things, "ring of light at": st["portal"]}, ensure_ascii=False), "speakers": ", ".join(speakers), "here": ", ".join(here), "marks": ", ".join(spots), "poses": ", ".join(POSES),
        "language": LANGS.get(language, LANGS["hi"]), "scene": json.dumps({k: sc[k] for k in ("title", "time", "summary", "things")} | {"number": number}, ensure_ascii=False, indent=1),
    }, schema, f"Scene {number}: {sc['title']}", lambda d: check_scene(d, here, set(spots), speakers), f"one scene as shots; on screen: {', '.join(here)}; speakers: {', '.join(speakers)}; marks: {', '.join(spots)}")  # fmt: skip
    if errors:
        run.on_step(f"Scene {number}", "warn", "; ".join(errors))
    return to_shots(data, number, set_name, spots, here, where)


def build_film(run: Run, series_id: str, number: int, language: str = "hi", only_place: str | None = None) -> dict:
    engine = run.engine
    series, ep = engine.series(series_id), json.loads(engine.episode_path(series_id, number).read_text())
    film_id = f"ep{number:02d}"
    root = engine.root / "films" / film_id
    places = list(dict.fromkeys(sc["place"] for sc in ep["outline"]))
    sets, images = {}, 0
    for place in places:
        if only_place and place != only_place:
            continue
        run.on_step(f"Set: {place}", "running")
        sets[slug(place)], made = build_place(run, place, [sc for sc in ep["outline"] if sc["place"] == place], root / "sets" / slug(place))
        images += made
        run.on_step(f"Set: {place}", "done", f"{made} images")
    run.stats["images"] = images
    if only_place:
        return {"sets": sets, "stats": run.stats}

    where = {"cris": [0.0, 0.0], "baba": [0.0, 0.0]}
    shots: list[dict] = []
    previous = "None: this is the first scene."
    for n, sc in enumerate(ep["outline"], start=1):
        run.on_step(f"Scene {n}", "running")
        scene_shots = write_scene(run, ep, series, sc, n, slug(sc["place"]), sets[slug(sc["place"])], previous, where, language)
        shots += scene_shots
        previous = lines_of(scene_shots) or sc["summary"]
        run.on_step(f"Scene {n}", "done", f"{len(scene_shots)} shots")
    first = shots[0]["place"]
    film = {"id": film_id, "title": ep["title"], "language": language, "cast": ["cris", "baba"], "names": NAMES, "voices": VOICES, "portal": [0, -3, 0], "sets": sets,
            "start": {who: {"x": (first.get(who) or [0, 0])[0], "z": (first.get(who) or [0, 0])[1], "pose": "stand", **({} if who in first else {"hidden": True})} for who in ("cris", "baba")}, "shots": shots}  # fmt: skip
    root.mkdir(parents=True, exist_ok=True)
    (root / "film.json").write_text(json.dumps(film, ensure_ascii=False, indent=1) + "\n")
    return {"film": film_id, "shots": len(shots), "stats": run.stats}
