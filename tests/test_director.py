"""The director's code checks and set builder, without a model, a browser or Sadhu."""

from __future__ import annotations

import json
from types import SimpleNamespace

from vector_director.director.pipeline import (
    account,
    apply_casting,
    Run,
    apply_direction,
    check_breakdown,
    check_direction,
    check_plan,
    check_scene,
    dress_set,
    en,
    free_mark,
    usable,
    write_episode,
)
from vector_director.director.setbuilder import (
    BACKGROUNDS,
    FAR,
    GROUND,
    ROOMS,
    backdrop,
    background,
    scale_for,
)
from vector_director.m1_harness.prop import PX_PER_CM

TPL = {"length": "6-8 scenes", "stages": [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "baba": True}]}


def plan():
    return {
        "cast": [{"id": "meera", "reuse": ""}, {"id": "baba", "reuse": "nobody"}],
        "sets": [{"id": "beach", "reuse": ""}],
        "scenes": [{"stage": "a", "set": "beach", "cast": ["meera"]}, {"stage": "b", "set": "beach", "cast": ["baba"]}],
    }


def test_plan_needs_enough_scenes_and_clears_unknown_reuse():
    p = plan()
    errors = check_plan(p, TPL, {"cast": {}, "sets": {}})
    assert p["cast"][1]["reuse"] == ""
    assert errors == ["the plan has 2 scenes but needs at least 6: split scenes by each change of place or time, and keep the story's events"]


def test_plan_catches_bad_ids():
    p = plan()
    p["scenes"][0]["set"] = "market"
    p["scenes"][1]["cast"] = ["ravi"]
    text = " ".join(check_plan(p, {"stages": TPL["stages"]}, {"cast": {}, "sets": {}}))
    assert 'uses set "market"' in text and 'has "ravi"' in text and 'needs Baba' in text


def test_scene_lines_must_be_in_hindi_and_by_the_cast():
    sc = {"cast": ["meera"]}
    beats = [{"type": "narration", "who": "x", "text": "एक दिन"}, {"type": "line", "who": "ravi", "text": "hello"}, {"type": "action", "who": "meera", "text": "walks"}]
    errors = check_scene({"beats": beats}, sc, "hi")
    assert beats[0]["who"] == "narrator"
    assert any('"ravi"' in e for e in errors) and any("Hindi" in e for e in errors)


def direction():
    return {
        "start": [{"who": "a", "mark": "back-left", "pose": "stand"}, {"who": "b", "mark": "back-left", "pose": "stand"}],
        "beats": [
            {"moves": [], "poses": [], "shot": "wide", "on": ""},
            {"moves": [{"who": "b", "to": "front-far-left"}], "poses": [], "shot": "close", "on": "a"},
        ],
    }


def test_direction_check_finds_a_speaker_off_stage():
    sc = {"cast": ["a"], "beats": [{"type": "line", "who": "a"}]}
    d = {"start": [{"who": "a", "mark": "off-left"}], "beats": [{"moves": [], "poses": [], "shot": "keep", "on": ""}]}
    assert check_direction(d, sc) == ["beat 1: a speaks but is off stage"]


def test_applying_direction_separates_people_and_faces_the_speaker():
    sc = {"beats": [{"type": "narration", "who": "narrator"}, {"type": "line", "who": "a"}]}
    apply_direction(direction(), sc, {}, {})
    start = sc["staging"]["cast"]
    assert start["a"]["x"] != start["b"]["x"]
    assert start["a"]["scale"] == 0.8
    assert sc["beats"][0]["stage"]["cam"] == {"shot": "wide"}
    second = sc["beats"][1]["stage"]
    assert second["move"]["b"] == {"x": 170, "y": 750}
    assert second["cam"] == {"shot": "close", "on": "a"}
    assert second["turn"] == {"a": -1}


def test_an_animal_waits_further_off_stage():
    sc = {"beats": [{"type": "narration", "who": "narrator"}]}
    d = {"start": [{"who": "camels", "mark": "off-right", "pose": "stand"}, {"who": "a", "mark": "off-right", "pose": "stand"}], "beats": [{"moves": [], "poses": [], "shot": "keep", "on": ""}]}
    apply_direction(d, sc, {}, {}, {"camels"})
    assert sc["staging"]["cast"]["camels"]["x"] == 2000 and sc["staging"]["cast"]["a"]["x"] == 1360


def test_emoji_stay_off_the_stage():
    assert not usable({"source": "openmoji", "kind": "prop"})
    assert usable({"source": "openclipart x", "kind": "prop"})


def test_every_backdrop_is_a_full_stage():
    for far in FAR:
        for ground in GROUND:
            svg = backdrop(far, ground, "x--y")
            assert svg.startswith("<svg") and 'viewBox="0 0 1200 800"' in svg and "set-night" in svg


def test_scale_is_real_size_but_stays_in_frame():
    pot = {"height_cm": 45, "drawn_cm": 45}
    assert scale_for(pot, "front", "outdoor", 640) == 0.8
    assert scale_for(pot, "back", "outdoor", 560) == 0.576
    tower = {"height_cm": 1000, "drawn_cm": 100}
    s = scale_for(tower, "front", "outdoor", 640)
    assert s * 100 * PX_PER_CM <= 601


def test_en_flattens_lists_and_keys():
    assert en("none", ["a"], {"b": 1})["enum"] == ["none", "a", "b"]


SPECIES = ["camel", "tiger"]


def outline():
    return {"title": "t", "logline": "l", "moral": "m", "scenes": [
        {"stage": "a", "title": "x", "place": "The town square", "time": "noon", "summary": "s", "mentioned": [],
         "present": [{"name": "Gopal", "what": "person"}, {"name": "camels", "what": "animal"}, {"name": "crow", "what": "animal"}], "things": ["shovel", "new pots"]},
    ]}  # fmt: skip


def casting():
    return {"cast": [{"id": "gopal", "kind": "person", "aka": ["Gopal"]}, {"id": "camels", "kind": "animal", "species": "camel", "aka": ["camels"]}],
            "pictures": [{"name": "crow", "aka": ["crow"]}], "places": [{"id": "square", "aka": ["town square"]}],
            "held": [{"who": "gopal", "thing": "shovel"}], "leftOut": [], "missing": []}  # fmt: skip


def test_casting_gives_every_name_a_home():
    plan, errors = apply_casting(outline(), casting(), SPECIES)
    assert errors == []
    sc = plan["scenes"][0]
    assert sc["set"] == "square" and sc["cast"] == ["gopal", "camels"]
    assert sc["things"] == ["crow", "new pots"]                       # a shovel in the hand isn't on the set


def test_casting_catches_a_lost_animal_and_an_unknown_species():
    c = casting()
    c["cast"] = c["cast"][:1]
    assert any('"camels" is present' in e for e in apply_casting(outline(), c, SPECIES)[1])
    c = casting()
    c["cast"][1]["species"] = "dragon"
    assert any("species must be one of" in e for e in apply_casting(outline(), c, SPECIES)[1])


def test_left_out_needs_a_reason_and_is_reported():
    o, c = outline(), casting()
    c["cast"] = c["cast"][:1]
    c["leftOut"] = [{"name": "camels", "why": "only heard"}]
    plan, errors = apply_casting(o, c, SPECIES)
    assert errors == []
    plan["scenes"][0]["number"] = 1
    report = account(plan["scenes"], [{"id": "square", "dressing": []}], [{"id": "gopal", "body3d": {"outfit": {"holdR": "spade"}}}], [])
    by = {r["name"]: r["status"] for r in report["rows"]}
    assert by == {"Gopal": "on screen", "camels": "left out", "crow": "lost", "shovel": "held", "new pots": "lost"}
    assert report["lost"] == 2


def test_breakdown_needs_enough_scenes_in_order():
    o = outline()
    o["scenes"] = [{**o["scenes"][0], "stage": "b"}, {**o["scenes"][0], "stage": "a"}]
    text = " ".join(check_breakdown(o, TPL))
    assert "comes after a later stage" in text and "needs at least 6" in text


class FakeRun:
    three_d = False

    """Answers the set builder's calls from a script, and searches a gallery of everything."""

    def __init__(self, answers):
        self.answers, self.wanted, self.files, self.steps = answers, [], {"sets": [], "objects": []}, []
        self.gallery = self
        self.reg = self
        self.engine = self
        self.menus = {"assets": {}}

    def on_step(self, *a):
        self.steps.append(a)

    def search(self, query, k=20):
        return [] if "unicorn" in query else [{"id": query.replace(" ", "-"), "name": query, "height_cm": 100, "drawn_cm": 100, "description": "", "kind": "prop", "source": "x"}]

    def svg_path(self, item):
        class P:
            read_text = staticmethod(lambda: "<svg/>")

        return P

    def ask(self, task, vars, schema, label):
        if task == "pick":
            return {"picks": [{"slug": s, "id": s} for s in self.pick_ids(vars["needs"])]}
        return self.answers.pop(0)

    @staticmethod
    def pick_ids(needs):
        return [line.strip()[2:].split(":")[0] for line in needs.splitlines() if line.startswith("- ")]


def thing(slug, row="back", mark="left", who=""):
    return {"slug": slug, "for": who, "query": slug.replace("-", " "), "prompt": "p", "height_cm": 100, "row": row, "mark": mark}


def test_a_return_visit_keeps_the_place_and_only_changes_what_it_says():
    run = FakeRun([
        {"background": "village-road", "things": [thing("stone-well"), thing("kiln", mark="left")]},
        {"remove": ["kiln"], "add": [thing("new-pots", "front", "right", "new pots"), thing("unicorn", "front", "left", "the unicorn")]},
    ])  # fmt: skip
    st = {"id": "yard", "name": "Yard", "kind": "outdoor"}
    scenes = [{"number": 2, "set": "yard", "time": "day", "summary": "", "beats": []}, {"number": 5, "set": "other"}, {"number": 8, "set": "yard", "time": "day", "summary": "", "beats": [], "things": ["new pots", "the unicorn", "a kite"]}]
    # the slugs double as gallery ids here
    for t in run.answers[0]["things"] + run.answers[1]["add"]:
        t["query"] = t["slug"]
    dress_set(run, "p", st, scenes)
    items = {d["need"]: d for d in st["dressing"]}
    assert st["background"] == "village-road" and st["art"] == "p--yard" and len(run.files["sets"]) == 1
    assert items["stone-well"]["scenes"] == []                         # in every scene here
    assert items["kiln"]["scenes"] == [2] and items["kiln"]["x"] != items["stone-well"]["x"]   # asked for a taken mark
    assert items["new-pots"]["scenes"] == [8] and items["new-pots"]["for"] == "new pots"
    assert {w["for"] for w in run.wanted} == {"the unicorn", "a kite"} and all(w["scene"] == 8 for w in run.wanted)


def test_a_place_from_the_library_keeps_what_it_has_and_adds_what_this_story_needs():
    run = FakeRun([{"remove": [], "add": [thing("oil-lamp", "front", "right", "oil lamp")]}])
    run.answers[0]["add"][0]["query"] = "oil-lamp"
    st = {"id": "court", "name": "Court", "kind": "outdoor", "reused": True, "art": "old", "dressing": [{"slug": "throne", "x": 600, "y": 560, "scale": 1, "scenes": [3]}]}
    dress_set(run, "p", st, [{"number": 7, "set": "court", "time": "day", "summary": "", "beats": [], "things": ["oil lamp"]}])
    assert st["art"] == "old" and {d["slug"] for d in st["dressing"]} == {"throne", "oil-lamp"} and not run.wanted


def test_free_mark_moves_along_the_row():
    assert free_mark("back", "left", [{"row": "back", "mark": "left"}, {"row": "front", "mark": "centre"}]) in ("far-left", "centre")
    assert free_mark("back", "left", []) == "left"


def test_every_named_background_draws_and_a_river_or_road_shows():
    for key in BACKGROUNDS:
        assert background(key, "x--y").startswith("<svg")
    assert "#3F7FA6" in background("village-river", "a") and "#3F7FA6" not in background("village", "a")
    assert "#D8C4A0" in background("village-road", "a")
    assert all(len(r) == 2 for r in ROOMS.values())


def test_a_rooms_spot_given_as_a_mark_still_places_the_thing():
    assert free_mark("front", "front-left", []) == "left"
    assert free_mark("back", "wall-center", []) == "centre"
    assert free_mark("back", "nonsense", []) == "centre"


def test_an_animal_cast_as_a_crowd_becomes_a_picture():
    outline = {"title": "t", "logline": "", "moral": "", "scenes": [{"stage": "s", "title": "t", "place": "yard", "time": "day", "summary": "", "present": [{"name": "crows", "what": "animal"}, {"name": "Ram", "what": "person"}]}]}
    casting = {"cast": [{"id": "crows", "name": "crows", "kind": "crowd", "aka": ["crows"]}, {"id": "ram", "name": "Ram", "kind": "person", "aka": ["Ram"]}], "places": [{"id": "yard", "name": "yard", "aka": ["yard"]}]}
    plan, errors = apply_casting(outline, casting, ["goat"])
    assert not errors and [c["id"] for c in plan["cast"]] == ["ram"] and plan["scenes"][0]["things"] == ["crows"] and plan["scenes"][0]["cast"] == ["ram"]


def test_animals_on_stage_keep_their_length_apart():
    sc = {"beats": []}
    d = {"start": [{"who": "cow", "mark": "back-centre"}, {"who": "tiger", "mark": "back-centre"}], "beats": []}
    apply_direction(d, sc, None, {}, {"cow", "tiger"})
    at = sc["staging"]["cast"]
    assert abs(at["cow"]["x"] - at["tiger"]["x"]) >= 300


def test_a_3d_project_is_dressed_from_the_catalog():
    run = FakeRun([{"background": "riverbank", "things": [thing("old-well") | {"item": "stone-well"}, thing("unicorn", mark="right") | {"item": "none"}]}])
    run.three_d = True
    run.menus = {"assets": {}, "animals": {"species": []}, "catalog3d": {"things": [{"id": "stone-well", "about": "a well", "height_cm": 180}], "places": ["riverbank"], "furniture": [], "animals": []}}
    st = {"id": "bank", "name": "Bank", "kind": "outdoor"}
    dress_set(run, "p", st, [{"number": 1, "set": "bank", "time": "day", "summary": "", "beats": [], "things": []}])
    assert [d["slug"] for d in st["dressing"]] == ["stone-well"] and st["background"] == "riverbank" and "art" not in st
    assert [w["slug"] for w in run.wanted] == ["unicorn"] and not run.files["sets"] and not run.files["objects"]


def test_an_episode_reads_the_series_and_what_came_before_and_saves_its_outline(tmp_path, monkeypatch):
    series = tmp_path / "bible" / "series" / "s"
    (tmp_path / "bible" / "templates").mkdir(parents=True)
    series.mkdir(parents=True)
    tpl = {"id": "t", "name": "T", "description": "d", "length": "1-2 scenes", "rules": ["r"], "stages": [{"id": "a", "name": "A", "scenes": [1, 2], "goal": "g"}]}
    (tmp_path / "bible" / "templates" / "t.json").write_text(json.dumps(tpl))
    (series / "series.json").write_text(json.dumps({"name": "S", "premise": "p", "dimensions": [], "characters": [], "rules": [], "episodes": {"2": {"template": "t", "brief": "b"}}}))
    (series / "ep01.json").write_text(json.dumps({"logline": "first logline"}))

    from vector_director.director.pipeline import Engine

    engine = Engine.__new__(Engine)
    engine.root, engine.menus = tmp_path, {"times": ["day"]}
    asked = []
    answers = {
        "episode": {"title": "E", "logline": "l", "moral": "m", "story": "once", "stages": []},
        "breakdown": {"title": "E", "logline": "l", "moral": "m", "scenes": [{"stage": "a", "title": "x", "place": "p", "time": "day", "summary": "s", "present": [{"name": "Cris", "what": "person"}], "things": [], "mentioned": []}]},
    }

    def fake(task, vars, *a, **k):
        asked.append((task, vars))
        return {"data": answers[task], "cached": False, "usage": {}, "provider": "gemini", "model": "m", "tries": []}

    monkeypatch.setattr("vector_director.director.pipeline.LLM", SimpleNamespace(run=fake, LLMError=Exception))
    out = write_episode(Run("p", engine, None), "s", 2, "en")
    assert [t for t, _ in asked] == ["episode", "breakdown"]
    assert "first logline" in asked[0][1]["previous"]
    assert json.loads((series / "ep02.json").read_text())["outline"] == out["outline"] == answers["breakdown"]["scenes"]
