"""From an episode's outline to a film. Studio holds the film as it's made, and a person finishes each part by hand.

    1. outline   `write_project` lays the episode out as a Studio project: its sets, each with what its scenes need.
    2. sets      someone builds each set in Studio. `write_scenes` stops until they all are.
    3. scenes    one call per scene, in story order, each reading the scene before: lines and staging together,
                 because both are picks from what the set and the engine have. A scene that already has shots is
                 kept, so that nothing edited by hand is lost, and a rerun only pays for what's missing.
    4. the film  someone edits and finalizes each scene and arranges them on the timeline. Studio composes the film,
                 and `save_film` writes it with its art copied in.

The answer is checked in code, then turned into sadhu's film format (schemas/film.schema.json).
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import urllib.request
from pathlib import Path

from PIL import Image

from vector_director.director.pipeline import DEVANAGARI, LANGS, N, Run, S, arr, en, obj

IMAGE_MODEL = "gpt-image-1.5"
STYLE = "Simple flat-colour cartoon, like a modern 2D animated TV series: big clean shapes, few details, a limited palette, soft gradient shading only, thin dark ink outlines. It sits beside smooth, simple 3D cartoon characters. No text, no people."
FAR_RULE = "A background seen straight on from eye level. It fills the whole picture and repeats nothing important at the edges. The bottom edge of the picture is exactly where it meets the ground: show no floor or ground at all."
PIECE_RULE = "One object alone, seen exactly straight on from eye level, so its top surface isn't visible, on a fully transparent background. Nothing beneath it: no ground, floor, grass, rubble or shadow."
FLOOR_RULE = "A seamless repeating ground texture, seen straight down from above, with even flat light and no objects or shadows: "
DEFAULT_MARKS = [{"name": "left", "x": -1.5, "z": 0}, {"name": "centre", "x": 0, "z": 0.5}, {"name": "right", "x": 1.5, "z": 0}]      # for a set given no marks of its own
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


def paint_new(folder: Path, name: str, kind: str, about: str) -> Path:
    "Paints one thing for the gallery, for Studio's Paint this button. -> the file, inside folder."
    folder.mkdir(parents=True, exist_ok=True)
    if kind == "backdrop":
        paint(path := folder / f"{slug(name)}.jpg", f"{about}\n\n{FAR_RULE}", "1536x1024")
    elif kind == "floor":
        paint(path := folder / f"{slug(name)}.jpg", FLOOR_RULE + about, "1024x1024")
    else:
        paint(path := folder / f"{slug(name)}.webp", f"{about}\n\n{PIECE_RULE}", "1024x1024", clear=True)
    return path


def project_id(series_id: str, number: int) -> str:
    return f"{series_id}-ep{number:02d}"


def write_project(engine, series_id: str, number: int, ep: dict) -> dict:
    "The outline as a Studio project. A set that's already been worked on keeps its work."
    path = engine.root / "projects" / project_id(series_id, number) / "project.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    kept = {st["id"]: st for st in old.get("sets", [])}
    written = {sc["number"]: sc for sc in old.get("scenes", []) if sc.get("title") in [o["title"] for o in ep["outline"]]}
    sets, scenes = {}, []
    for n, sc in enumerate(ep["outline"], start=1):
        sid = slug(sc["place"])
        st = sets.setdefault(sid, kept.get(sid, {"id": sid, "name": sc["place"], "items": [], "marks": [], "built": False}))
        scenes.append({"number": n, "id": f"s{n:02d}", "stage": sc["stage"], "title": sc["title"], "set": sid, "time": sc["time"], "summary": sc["summary"], "things": sc["things"], "cast": [slug(x["name"]) for x in sc["present"]],
                       **({"shots": written[n]["shots"], "final": written[n].get("final", False)} if n in written and written[n].get("shots") else {})})  # fmt: skip
    project = {**old, "id": project_id(series_id, number), "series": series_id, "episode": number, "mode": "3d", "title": ep["title"], "language": ep.get("language", "hi"), "template": ep["template"],
               "story": ep["story"], "logline": ep["logline"], "moral": ep.get("moral", ""), "filmCast": sorted(ON_SCREEN), "names": NAMES, "voices": VOICES, "sets": list(sets.values()), "scenes": scenes}  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project, ensure_ascii=False, indent=1) + "\n")
    return project


def unbuilt(project: dict) -> list[str]:
    "The sets still to build, by name."
    return [st["name"] for st in project["sets"] if not st.get("built")]


def film_set(st: dict) -> dict:
    "What a scene is written against: a built set's things, its marks, and where a ring of light opens."
    items = st.get("items", [])
    door = next((it for it in items if re.search("arch|gate|door|portal", it["name"], re.I)), None)     # a ring of light opens in a doorway, if the place has one
    return {"items": items, "marks": [{k: m[k] for k in ("name", "x", "z")} for m in st.get("marks", [])] or DEFAULT_MARKS, "portal": [door["x"], door["z"] + 0.05] if door else [0, -2]}


def save_film(engine, library: Path, film: dict) -> dict:
    "A film as Studio composed it, with its art copied in, so that it keeps working whatever the gallery does later."
    if not re.fullmatch("[a-z0-9-]+", film.get("id", "")):
        raise ValueError("a film needs an id")
    root = engine.root / "films" / film["id"]
    for sid, st in film["sets"].items():
        folder = root / "sets" / slug(sid)
        folder.mkdir(parents=True, exist_ok=True)
        base = st.get("base") or {}
        for file in [base.get("backdrop"), base.get("floor"), *[it.get("file") for it in st.get("items", []) if it["format"] != "3d"]]:
            if file:
                shutil.copyfile(library / "items" / Path(file).name, folder / Path(file).name)
    (root / "film.json").write_text(json.dumps(film, ensure_ascii=False, indent=1) + "\n")
    return {"film": film["id"], "shots": len(film["shots"])}


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
            errors.append(f"shot {n}: {c} needs two people, and {here[0] if here else 'nobody'} is here")
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
    things = [{"name": it["name"], "x": it["x"], "z": it["z"]} for it in st["items"]]
    data, errors = run.checked("film_scene", {
        "series": series["name"], "about": json.dumps({k: series[k] for k in ("premise", "characters", "rules")}, ensure_ascii=False, indent=1), "story": ep["story"], "previous": previous,
        "set": json.dumps({"place": sc["place"], "things": things, "ring of light at": st["portal"]}, ensure_ascii=False), "speakers": ", ".join(speakers), "here": ", ".join(here), "marks": ", ".join(spots), "poses": ", ".join(POSES),
        "language": LANGS.get(language, LANGS["hi"]), "scene": json.dumps({k: sc[k] for k in ("title", "time", "summary", "things")} | {"number": number}, ensure_ascii=False, indent=1),
    }, schema, f"Scene {number}: {sc['title']}", lambda d: check_scene(d, here, set(spots), speakers), f"one scene as shots; on screen: {', '.join(here)}; speakers: {', '.join(speakers)}; marks: {', '.join(spots)}")  # fmt: skip
    if errors:
        run.on_step(f"Scene {number}", "warn", "; ".join(errors))
    return to_shots(data, number, set_name, spots, here, where)


def write_scenes(run: Run, series_id: str, number: int, language: str = "hi", only: int | None = None) -> dict:
    "Writes every scene that has no shots yet, or just the one asked for, and saves each as it's done."
    engine = run.engine
    series, ep = engine.series(series_id), json.loads(engine.episode_path(series_id, number).read_text())
    project = write_project(engine, series_id, number, ep)
    if waiting := unbuilt(project):
        run.on_step("Sets", "warn", "Still to build: " + ", ".join(waiting))
        return {"waiting": waiting, "stats": run.stats}
    path = engine.root / "projects" / project["id"] / "project.json"
    sets = {st["id"]: film_set(st) for st in project["sets"]}
    where = {"cris": [0.0, 0.0], "baba": [0.0, 0.0]}
    previous = "None: this is the first scene."
    wrote = 0
    for n, (sc, scene) in enumerate(zip(ep["outline"], project["scenes"], strict=True), start=1):
        if scene.get("final") or (scene.get("shots") and only != n) or (only and only != n):     # a finished scene is never written over
            for shot in scene.get("shots", []):
                where.update(shot.get("place") or {})
                for beat in shot["beats"]:
                    where.update(beat.get("walk") or {})
        else:
            run.on_step(f"Scene {n}", "running")
            scene["shots"] = write_scene(run, ep, series, sc, n, scene["set"], sets[scene["set"]], previous, where, language)
            path.write_text(json.dumps(project, ensure_ascii=False, indent=1) + "\n")
            wrote += 1
            run.on_step(f"Scene {n}", "done", f"{len(scene['shots'])} shots")
        previous = lines_of(scene.get("shots", [])) or sc["summary"]
    return {"wrote": wrote, "stats": run.stats}
