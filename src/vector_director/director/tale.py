"""A one-off story, as Guru writes it (POST /tale), made ready for Studio's own flow.

    1. outline   the story broken into scenes on its template (`spine` by default), as an episode is
    2. casting   everyone seen gets a person in sadhu's shared cast (cast/cast.json): one already there by the same name,
                 or a new one, picked from what Studio's Characters page offers (body, hair, clothes, colours, a voice)
    3. a series  the story is written as a series of one episode, with its own cast, names, voices and language, so
                 Studio's flow follows as for any episode: build its sets, then Write scenes (/film). Its film is named
                 after the story (the project's `film`), not ep01.
    4. bodies    each new person's MakeHuman body, built in Blender (tools/make_cast.py), a few minutes each

Running it again for the same id writes the outline and the project again (sets already built keep their work, as
`write_project` does) and the story's own people over; the shared cast's others are never touched.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from vector_director.director.film import project_id, slug, unbuilt, write_project
from vector_director.director.pipeline import LANGS, B, Run, S, arr, break_down, en, name_key, obj

HAIR = ["short01", "short02", "short03", "short04", "afro01", "bob01", "bob02", "braid01", "long01", "ponytail01"]
AGE = {"child": 0.12, "young": 0.42, "adult": 0.6, "old": 0.88}                  # MakeHuman's age: 0.5 is 25 years
BUILD = {"thin": (0.3, 0.4), "average": (0.5, 0.5), "heavy": (0.8, 0.45)}        # weight, muscle
SKIN = {"fair": 0xF1C9A5, "light": 0xE0AC85, "medium": 0xC68F67, "brown": 0xA86E48, "dark": 0x7A4B2E, "deep": 0x55321F}
HAIR_COLOUR = {"black": 0x141414, "dark brown": 0x3A2618, "brown": 0x6B4423, "auburn": 0x8A3B1E, "blonde": 0xD8B56A, "grey": 0x9A9A9A, "white": 0xEEEEEE}
COLOUR = {"white": 0xF2F0EA, "cream": 0xEAD9B5, "grey": 0x8C8C8C, "black": 0x222222, "navy": 0x223355, "blue": 0x3366AA, "sky blue": 0x7FB2DD,
          "green": 0x3C7A45, "olive": 0x6B6B33, "yellow": 0xE3C23A, "saffron": 0xE38B1F, "orange": 0xD9652B, "red": 0xB8342E, "maroon": 0x6E2230,
          "pink": 0xDD8AA6, "purple": 0x6A4C93, "brown": 0x6B4A2E, "khaki": 0xB5A27A}  # fmt: skip
OUTFITS = {          # what a person wears: wardrobe names (assets3d/wardrobe), shoes added unless barefoot
    "kurta and pyjama": ["sadhu_pyjama", "sadhu_kurta"], "dhoti and kurta": ["sadhu_dhoti", "sadhu_kurta"],
    "robe": ["sadhu_robe"], "dhoti and shawl": ["sadhu_dhoti", "sadhu_shawl"],
    "casual (man)": ["male_casualsuit01"], "casual 2 (man)": ["male_casualsuit03"], "casual 3 (man)": ["male_casualsuit05"],
    "work clothes (man)": ["male_worksuit01"], "suit (man)": ["male_elegantsuit01"],
    "casual (woman)": ["female_casualsuit01"], "casual 2 (woman)": ["female_casualsuit02"], "smart (woman)": ["female_elegantsuit01"], "sports (woman)": ["female_sportsuit01"],
}  # fmt: skip
BAREFOOT = {"dhoti and shawl", "robe"}
VOICES = {           # Gemini's voices, and how each sounds
    "Puck": "upbeat man", "Charon": "informative, deep man", "Fenrir": "excitable man", "Orus": "firm man", "Iapetus": "clear man",
    "Algenib": "gravelly older man", "Enceladus": "breathy, soft man", "Algieba": "smooth man", "Sadaltager": "knowledgeable man",
    "Kore": "firm woman", "Zephyr": "bright woman", "Leda": "youthful woman", "Aoede": "breezy woman", "Autonoe": "bright young woman",
    "Achernar": "soft woman", "Gacrux": "mature woman", "Sulafat": "warm woman", "Callirrhoe": "easy-going woman",
}  # fmt: skip
SAY = {"en": {"male": "Eddy (English (US))", "female": "Flo (English (US))"}, "hi": {"male": "Lekha", "female": "Lekha"}}
NARRATOR = {"say": {"voice": "Eddy (English (US))", "rate": 170, "pitch": 0.95}, "gemini": {"voice": "Iapetus", "note": "warm storyteller"}}
STAGING = ("They can walk, talk, gesture and react. Don't write anything that needs them to carry, fight, climb, sit, fall or touch "
           "things: say it through what they say and how they move between marks.")


def cast_schema() -> dict:
    return obj({"cast": arr(obj({
        "name": S, "aka": arr(S), "reuse": S, "about": S,
        "gender": en("male", "female"), "age": en(list(AGE)), "build": en(list(BUILD)), "skin": en(list(SKIN)),
        "hair": en([*HAIR, "bald"]), "hairColour": en(list(HAIR_COLOUR)), "beard": B,
        "outfit": en(list(OUTFITS)), "top": en(list(COLOUR)), "lower": en(list(COLOUR)),
        "voice": en(list(VOICES)), "voiceNote": S}))})  # fmt: skip


def seen_people(outline: dict) -> list[str]:
    "Everyone seen in a scene as a person, by the outline's own names, once each."
    return list(dict.fromkeys(p["name"] for sc in outline["scenes"] for p in sc["present"] if p.get("what", "person") == "person"))


def check_cast(c: dict, seen: list[str], shared: dict) -> list[str]:
    errors, homes = [], {}
    for entry in c["cast"]:
        for n in [entry["name"], *entry.get("aka", [])]:
            homes[name_key(n)] = entry["name"]
        if entry.get("reuse") and entry["reuse"] not in shared:
            errors.append(f'"{entry["name"]}": reuse must be one of {", ".join(shared)} or ""')
    errors += [f'"{n}" is seen in the outline but in no cast entry\'s name or aka' for n in seen if name_key(n) not in homes]
    return errors


def person(entry: dict) -> dict:
    "A cast.json person from the casting's picks."
    weight, muscle = BUILD[entry["build"]]
    hair, top, low = HAIR_COLOUR[entry["hairColour"]], COLOUR[entry["top"]], COLOUR[entry["lower"]]
    worn = OUTFITS[entry["outfit"]]
    clothes = [{"name": w, "color": low if w in ("sadhu_pyjama", "sadhu_dhoti") else top} for w in worn]
    if entry["outfit"] not in BAREFOOT:
        clothes.append({"name": "shoes06", "color": 0x3B2A1E})
    bald = entry["hair"] == "bald"
    return {
        "name": entry["name"],
        "build": {"gender": 1 if entry["gender"] == "male" else 0, "age": AGE[entry["age"]], "weight": weight, "muscle": muscle,
                  "race": {"asian": 0.5, "caucasian": 0.3, "african": 0.2}, "skin": "toon01", "eyes": "high-poly", "eyebrows": "eyebrow001",
                  "eyelashes": "eyelashes01", "hair": "short02" if bald else entry["hair"], "clothes": []},
        "shape": {},
        "wear": {"skin": SKIN[entry["skin"]], "wear": top, "low": low, "hair": hair, "clothes": clothes},
        "head": {"brow": hair, "eye": {"iris": 0x3D2614}, **({"bald": True} if bald else {}),
                 **({"beard": True, "beardColor": hair} if entry.get("beard") and entry["gender"] == "male" else {})},
        "about": entry.get("about", ""),
    }  # fmt: skip


def voice(entry: dict, language: str) -> dict:
    return {"say": {"voice": SAY.get(language, SAY["en"])[entry["gender"]], "rate": 175, "pitch": 1.0},
            "gemini": {"voice": entry["voice"], "note": entry.get("voiceNote") or VOICES[entry["voice"]]}}


def write_tale(run: Run, req: dict, build_bodies: bool = True) -> dict:
    """Guru's story -> a series of one episode, its people in the shared cast, and its Studio project waiting for sets.
    req: {"id", "title", "story", "logline", "moral", "language", "people": [{"name", "about"}], "template"}"""
    engine, on_step = run.engine, run.on_step
    tid = slug(req.get("id") or req["title"])
    if not tid:
        raise ValueError("a story needs an id or a title")
    folder = engine.root / "bible" / "series" / tid
    if (folder / "series.json").exists() and not json.loads((folder / "series.json").read_text()).get("tale"):
        raise ValueError(f'"{tid}" is a series of its own: give the story another id')
    language = req.get("language") or "en"
    tpl = engine.template(req.get("template") or "spine")
    outline = break_down(run, req["story"], req["title"], LANGS.get(language, LANGS["en"]), tpl)

    # the cast: everyone seen, in the shared cast
    cast_file = engine.root / "cast" / "cast.json"
    shared = json.loads(cast_file.read_text()) if cast_file.exists() else {}
    seen = seen_people(outline)
    on_step("Casting", "running")
    people = "\n".join(f"- {p['name']}: {p.get('about', '')}" for p in req.get("people") or []) or "None given."
    others = "\n".join(f"- {k}: {v.get('name', k)}" for k, v in shared.items() if v.get("kind") != "animal" and not k.startswith(f"{tid}-"))
    casting, errors = run.checked("tale_cast", {
        "language": LANGS.get(language, LANGS["en"]), "title": req["title"], "story": req["story"], "people": people, "seen": "\n".join(f"- {n}" for n in seen),
        "shared": others or "Nobody yet.", "hair": ", ".join([*HAIR, "bald"]), "outfits": ", ".join(OUTFITS), "voices": "\n".join(f"- {k}: {v}" for k, v in VOICES.items()),
    }, cast_schema(), "Casting", lambda c: check_cast(c, seen, shared), "the casting of a story; every name seen must be in an entry's name or aka: " + ", ".join(seen))  # fmt: skip
    if errors:
        on_step("Casting", "failed", "; ".join(errors))
        raise RuntimeError(f"The casting still has problems: {'; '.join(errors)}")
    ids, names, voices, new = {}, {}, {"narrator": NARRATOR}, []
    for entry in casting["cast"]:
        cid = entry["reuse"] or f"{tid}-{slug(entry['name'])}"
        for n in [entry["name"], *entry.get("aka", [])]:
            ids[name_key(n)] = cid
        names[cid] = entry["name"]
        voices[cid] = voice(entry, language)
        if not entry["reuse"]:
            shared[cid] = person(entry)
            new.append(cid)
    on_screen = sorted({ids[name_key(n)] for n in seen})
    tmp = cast_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(shared, ensure_ascii=False, indent=1) + "\n")
    os.replace(tmp, cast_file)
    on_step("Casting", "done", f"{len(on_screen)} on screen, {len(new)} new")

    # the series of one episode, and its project
    series = {"id": tid, "name": req["title"], "tale": True, "premise": req.get("logline") or outline["logline"], "dimensions": [],
              "characters": [{"id": cid, "name": names[cid], "about": shared.get(cid, {}).get("about", "")} for cid in on_screen],
              "rules": [STAGING], "episodes": {"1": {"template": tpl["id"], "brief": req.get("logline") or outline["logline"]}},
              "film": {"onScreen": on_screen, "names": names, "voices": voices, "heard": {}, "ids": ids, "sceneRules": []}}  # fmt: skip
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "series.json").write_text(json.dumps(series, ensure_ascii=False, indent=1) + "\n")
    ep = {"series": tid, "number": 1, "template": tpl["id"], "language": language, "title": req["title"],
          "logline": req.get("logline") or outline["logline"], "moral": req.get("moral") or outline.get("moral", ""),
          "story": req["story"], "stages": [], "outline": outline["scenes"]}  # fmt: skip
    (folder / "ep01.json").write_text(json.dumps(ep, ensure_ascii=False, indent=1) + "\n")
    project = write_project(engine, tid, 1, ep, series)

    # the new people's bodies
    built = []
    for cid in new if build_bodies else []:
        label = f"Body: {names[cid]}"
        on_step(label, "running", "Blender, a few minutes")
        r = subprocess.run([sys.executable, "tools/make_cast.py", cid], cwd=engine.root, capture_output=True, text=True, timeout=1800, check=False)
        if r.returncode:
            run.stats["failed"].append(label)
            on_step(label, "failed", (r.stdout + r.stderr).strip()[-300:])
        else:
            built.append(cid)
            on_step(label, "done")
    return {"project": project_id(tid, 1), "film": tid, "title": req["title"], "cast": on_screen, "new": new, "built": built,
            "sets": unbuilt(project), "scenes": len(project["scenes"]), "stats": run.stats}  # fmt: skip

