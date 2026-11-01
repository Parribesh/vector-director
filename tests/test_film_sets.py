"""A film waits for its sets, and takes its art from what was built."""

import json

from vector_director.director.film import film_sets, unbuilt, write_project


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


def test_film_sets_copy_art_and_find_the_doorway(tmp_path):
    (tmp_path / "items").mkdir()
    for f in ("arch.webp", "far.jpg", "pot.svg"):
        (tmp_path / "items" / f).write_text("x")
    item = {"x": 1, "z": -2, "height_m": 2}
    project = {"sets": [{"id": "cave", "name": "Cave", "base": {"sky": "dusk", "backdrop": "far.jpg"}, "items": [
        {**item, "id": "arch", "name": "stone arch", "format": "image", "file": "arch.webp"},
        {**item, "id": "pot", "name": "pot", "format": "svg", "file": ""},
        {**item, "id": "hut", "name": "hut", "format": "3d"},
    ], "marks": []}]}  # fmt: skip
    out = film_sets(project, tmp_path, tmp_path / "film")["cave"]
    assert (tmp_path / "film/sets/cave/far.jpg").exists() and (tmp_path / "film/sets/cave/pot.svg").exists()
    assert out["items"][1]["file"] == "pot.svg" and "file" not in out["items"][2]
    assert out["portal"] == [1, -1.95] and len(out["marks"]) == 3
