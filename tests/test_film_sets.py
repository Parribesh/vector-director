"""A film waits for its sets, and takes its art from what was built."""

import json

from vector_director.director.film import film_set, save_film, unbuilt, write_project


class FakeEngine:
    def __init__(self, root):
        self.root = root


EP = {"title": "T", "template": "t", "story": "s", "logline": "l", "language": "en", "outline": [
    {"stage": "a", "title": "One", "place": "Old Cave", "time": "day", "summary": "x", "things": ["arch"], "present": [{"name": "Cris"}]},
    {"stage": "b", "title": "Two", "place": "River", "time": "day", "summary": "y", "things": [], "present": [{"name": "Baba"}]},
    {"stage": "c", "title": "Three", "place": "Old Cave", "time": "night", "summary": "z", "things": [], "present": []},
]}  # fmt: skip


def test_outline_makes_a_set_per_place_and_keeps_work(tmp_path):
    p = write_project(FakeEngine(tmp_path), "s", 1, EP)
    assert [s["id"] for s in p["sets"]] == ["old-cave", "river"]
    assert [sc["set"] for sc in p["scenes"]] == ["old-cave", "river", "old-cave"]
    assert unbuilt(p) == ["Old Cave", "River"]
    p["sets"][0].update(built=True, items=[{"uid": "a"}])
    (tmp_path / "projects/s-ep01/project.json").write_text(json.dumps(p))
    again = write_project(FakeEngine(tmp_path), "s", 1, EP)
    assert again["sets"][0]["items"] == [{"uid": "a"}] and unbuilt(again) == ["River"]


def test_outline_keeps_written_scenes(tmp_path):
    p = write_project(FakeEngine(tmp_path), "s", 1, EP)
    p["scenes"][1].update(shots=[{"id": "x"}], final=True)
    (tmp_path / "projects/s-ep01/project.json").write_text(json.dumps(p))
    again = write_project(FakeEngine(tmp_path), "s", 1, EP)
    assert again["scenes"][1]["final"] and "shots" not in again["scenes"][0]


def test_saved_film_brings_its_art_and_a_set_finds_its_doorway(tmp_path):
    (tmp_path / "items").mkdir()
    for f in ("arch.webp", "far.jpg", "pot.svg"):
        (tmp_path / "items" / f).write_text("x")
    item = {"x": 1, "z": -2, "height_m": 2}
    st = {"id": "cave", "items": [{**item, "name": "stone arch", "format": "image", "file": "arch.webp"}, {**item, "name": "pot", "format": "svg", "file": "pot.svg"}, {**item, "name": "hut", "format": "3d"}], "marks": []}
    assert film_set(st)["portal"] == [1, -1.95] and len(film_set(st)["marks"]) == 3
    film = {"id": "ep01", "sets": {"cave": {"base": {"backdrop": "far.jpg"}, **film_set(st)}}, "shots": []}
    save_film(FakeEngine(tmp_path), tmp_path, film)
    assert (tmp_path / "films/ep01/sets/cave/far.jpg").exists() and (tmp_path / "films/ep01/sets/cave/pot.svg").exists()
    assert json.loads((tmp_path / "films/ep01/film.json").read_text())["id"] == "ep01"
