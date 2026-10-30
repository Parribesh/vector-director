"""The director's code checks and set builder, without a model, a browser or Sadhu."""

from __future__ import annotations

from vector_director.director.pipeline import (
    apply_direction,
    check_direction,
    check_plan,
    check_scene,
    en,
    usable,
)
from vector_director.director.setbuilder import FAR, GROUND, backdrop, scale_for
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
