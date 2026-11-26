"""A one-off story (POST /tale): outlined, cast into the shared cast, written as a series of one episode with its own
cast and language, and its project waiting for sets. A fake model; no Blender."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from vector_director.director.film import check_scene, film_cast, write_project
from vector_director.director.pipeline import Engine, Run
from vector_director.director.tale import write_tale

SPINE = {"id": "spine", "name": "Spine", "description": "d", "length": "2-3 scenes", "rules": [],
         "stages": [{"id": "before", "name": "Before", "scenes": [1, 1], "goal": "g"}, {"id": "after", "name": "After", "scenes": [1, 1], "goal": "g"}]}
OUTLINE = {"title": "The Kite", "logline": "Asha finds her kite.", "moral": "m", "scenes": [
    {"stage": "before", "title": "Lost", "place": "rooftop", "time": "day", "summary": "s",
     "present": [{"name": "Asha", "what": "person"}, {"name": "Grandpa", "what": "person"}, {"name": "pigeons", "what": "animal"}], "things": ["kite"], "mentioned": []},
    {"stage": "after", "title": "Found", "place": "lane", "time": "day", "summary": "s", "present": [{"name": "the girl", "what": "person"}], "things": [], "mentioned": []}]}
CAST = {"cast": [
    {"name": "Asha", "aka": ["the girl"], "reuse": "", "about": "a girl", "gender": "female", "age": "child", "build": "thin", "skin": "brown",
     "hair": "braid01", "hairColour": "black", "beard": False, "outfit": "casual (woman)", "top": "yellow", "lower": "blue", "voice": "Leda", "voiceNote": "quick"},
    {"name": "Grandpa", "aka": [], "reuse": "baba", "about": "her grandfather", "gender": "male", "age": "old", "build": "average", "skin": "brown",
     "hair": "bald", "hairColour": "white", "beard": True, "outfit": "dhoti and shawl", "top": "cream", "lower": "white", "voice": "Algenib", "voiceNote": ""}]}


@pytest.fixture
def sadhu(tmp_path, monkeypatch):
    (tmp_path / "bible" / "templates").mkdir(parents=True)
    (tmp_path / "bible" / "templates" / "spine.json").write_text(json.dumps(SPINE))
    (tmp_path / "cast").mkdir()
    (tmp_path / "cast" / "cast.json").write_text(json.dumps({"baba": {"name": "Baba"}, "cris": {"name": "Cris"}}))
    engine = Engine.__new__(Engine)
    engine.root, engine.menus = tmp_path, {"times": ["day"]}
    asked = []

    def fake(task, vars, *a, **k):
        asked.append(task)
        return {"data": {"breakdown": OUTLINE, "tale_cast": CAST}[task], "cached": False, "usage": {}, "provider": "gemini", "model": "m", "tries": []}

    monkeypatch.setattr("vector_director.director.pipeline.LLM", SimpleNamespace(run=fake, LLMError=Exception))
    return SimpleNamespace(root=tmp_path, engine=engine, asked=asked)


def test_a_tale_is_a_series_of_one_with_its_own_people_and_a_project_waiting_for_sets(sadhu):
    out = write_tale(Run("the-kite", sadhu.engine, None), {"id": "the-kite", "title": "The Kite", "story": "once", "language": "en",
                                                          "people": [{"name": "Asha", "about": "a girl"}]}, build_bodies=False)
    assert sadhu.asked == ["breakdown", "tale_cast"]
    assert out["project"] == "the-kite-ep01" and out["film"] == "the-kite" and out["cast"] == ["baba", "the-kite-asha"]
    assert out["new"] == ["the-kite-asha"] and out["sets"] == ["rooftop", "lane"]
    cast = json.loads((sadhu.root / "cast" / "cast.json").read_text())
    assert cast["baba"] == {"name": "Baba"} and cast["the-kite-asha"]["build"]["gender"] == 0
    assert cast["the-kite-asha"]["build"]["hair"] == "braid01" and cast["the-kite-asha"]["wear"]["clothes"][0]["name"] == "female_casualsuit01"
    project = json.loads((sadhu.root / "projects" / "the-kite-ep01" / "project.json").read_text())
    assert project["film"] == "the-kite" and project["series"] == "the-kite" and project["language"] == "en"
    assert project["filmCast"] == ["baba", "the-kite-asha"] and project["names"]["the-kite-asha"] == "Asha"
    assert project["voices"]["the-kite-asha"]["gemini"]["voice"] == "Leda"
    assert project["scenes"][0]["cast"] == ["the-kite-asha", "baba", "pigeons"] and project["scenes"][1]["cast"] == ["the-kite-asha"]
    series = json.loads((sadhu.root / "bible" / "series" / "the-kite" / "series.json").read_text())
    assert series["tale"] and series["episodes"]["1"]["template"] == "spine"


def test_a_tale_never_writes_over_a_real_series(sadhu):
    (sadhu.root / "bible" / "series" / "cris-and-baba").mkdir(parents=True)
    (sadhu.root / "bible" / "series" / "cris-and-baba" / "series.json").write_text(json.dumps({"name": "Cris and Baba"}))
    with pytest.raises(ValueError, match="series of its own"):
        write_tale(Run("x", sadhu.engine, None), {"id": "cris-and-baba", "title": "T", "story": "s"}, build_bodies=False)


def test_cris_and_baba_keep_their_cast_and_hindi():
    fc = film_cast({"name": "Cris and Baba"})
    assert fc["onScreen"] == {"baba", "cris"} and "archway" in " ".join(fc["rules"])
    d = {"start": [{"who": "asha", "mark": "left", "pose": "stand"}],
         "shots": [{"camera": "wide", "beats": [{"who": "asha", "say": "Hello there", "walker": "none"}] * 3}] * 2}
    assert check_scene(d, ["asha"], {"left"}, ["asha", "narrator"], "en") == []
    assert any("Hindi" in e for e in check_scene(d, ["asha"], {"left"}, ["asha", "narrator"], "hi"))


def test_an_episode_project_has_no_film_of_its_own(tmp_path):
    engine = SimpleNamespace(root=tmp_path)
    ep = {"title": "E", "template": "t", "story": "s", "logline": "l", "outline": [
        {"stage": "a", "title": "x", "place": "p", "time": "day", "summary": "s", "present": [{"name": "Cris", "what": "person"}], "things": []}]}
    p = write_project(engine, "cris-and-baba", 1, ep)
    assert "film" not in p and p["filmCast"] == ["baba", "cris"] and p["scenes"][0]["cast"] == ["cris"]
