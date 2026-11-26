"""Paintings join the gallery, and a 2D story doesn't pick them."""

from __future__ import annotations

import json

from PIL import Image

from vector_director.director.pipeline import usable
from vector_director.m2_retrieval.library import Registry, seed_paintings


def test_a_films_painted_layers_become_items_only_once(tmp_path):
    folder = tmp_path / "sadhu" / "films" / "ep01" / "sets" / "river-clearing"
    folder.mkdir(parents=True)
    Image.new("RGB", (30, 20), "blue").save(folder / "backdrop.jpg")
    Image.new("RGB", (20, 20), "green").save(folder / "floor.jpg")
    Image.new("RGBA", (10, 20), (9, 9, 9, 255)).save(folder / "piece0.webp")
    (folder / "plan.json").write_text(json.dumps({"backdrop": "a river", "floor": "short grass", "pieces": [{"name": "Tall Reeds", "prompt": "reeds", "height_m": 1.5}]}))
    reg = Registry(tmp_path / "library")
    assert seed_paintings(reg, tmp_path / "sadhu") == {"paintings": 3}
    assert seed_paintings(reg, tmp_path / "sadhu") == {"paintings": 0}
    reeds = reg.items["paint-river-clearing-tall-reeds"]
    assert (reeds.format, reeds.kind, reeds.height_cm) == ("image", "prop", 150)
    assert (reg.root / "items" / reeds.file).exists() and reg.thumb_path(reeds.id).exists()
    assert reg.items["paint-river-clearing-floor"].kind == "floor"
    assert not usable({"kind": "prop", "format": "image", "source": "x"}) and usable({"kind": "prop", "source": "x"})
