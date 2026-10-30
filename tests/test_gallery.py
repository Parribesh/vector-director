"""The gallery without a browser or CLIP: registry edits, keyword search, fusion, licence filter."""

from __future__ import annotations

import pytest

from vector_director.core import Hit
from vector_director.m2_retrieval.library import Item, Registry, openmoji_entries, recolorable, tidy
from vector_director.m2_retrieval.retrievers import BM25Retriever, HybridRetriever


@pytest.fixture
def reg(tmp_path):
    r = Registry(tmp_path)
    r.add(Item(id="well", name="stone well", tags=["water"]), "<svg/>")
    r.add(Item(id="pot", name="clay pot", tags=["water", "kitchen"]), "<svg/>")
    r.add(Item(id="hill", name="hill", kind="backdrop"), "<svg/>")
    r.save()
    return r


def test_edits_survive_a_reload(reg, tmp_path):
    reg.update("well", height_cm=220, status="candidate", tags=["deep"])
    again = Registry(tmp_path)
    assert (again.items["well"].height_cm, again.items["well"].status, again.items["well"].tags) == (220, "candidate", ["deep"])


@pytest.mark.parametrize("bad", [{"height_cm": 0}, {"height_cm": "tall"}, {"status": "maybe"}, {"tags": "a,b"}])
def test_bad_edits_are_refused(reg, bad):
    with pytest.raises(ValueError):
        reg.update("well", **bad)


def test_bm25_finds_words_and_filters_kind(reg):
    r = BM25Retriever(reg)
    assert r.search("stone")[0].id == "well"
    assert {h.id for h in r.search("water")} == {"well", "pot"}
    assert r.search("hill", kind="prop") == []


def test_bm25_sees_an_edit_after_refresh(reg):
    r = BM25Retriever(reg)
    reg.update("pot", name="matka")
    r.refresh()
    assert r.search("matka")[0].id == "pot"


def test_hybrid_rewards_agreement():
    class Fixed:
        def __init__(self, ids):
            self.ids = ids

        def search(self, query, k=10, **kw):
            return [Hit(id=i, score=1.0) for i in self.ids[:k]]

    out = HybridRetriever([Fixed(["a", "b"]), Fixed(["b", "c"])]).search("x")
    assert next(h.id for h in out) == "b"


def test_openmoji_keeps_single_objects_only():
    base = {"group": "objects", "subgroups": "household", "hexcode": "1F9FA", "annotation": "basket"}
    keep = openmoji_entries(
        [
            base,
            {**base, "annotation": "cow face", "group": "animals-nature", "subgroups": "animal-mammal"},
            {**base, "group": "flags"},
            {**base, "hexcode": "1F9FA-200D"},
            {**base, "skintone": "1F3FB"},
        ]
    )
    assert [m["annotation"] for m in keep] == ["basket"]


def test_recolorable_keeps_its_look_and_shades_follow():
    svg = '<path fill="#8B5A2B"/><path fill="#8B5A2B"/><path fill="#56381b"/><path fill="#2a7f7a"/><path fill="#000"/><path style="stroke:#fff"/>'
    out, palette = recolorable(svg)
    assert palette == {"c1": "#8b5a2b", "c2": "#2a7f7a"}
    assert 'fill="var(--c1,#8b5a2b)"' in out
    assert 'fill="color-mix(in srgb,var(--c1,#' in out and "%,black)" in out
    assert 'fill="#000"' in out and "stroke:#fff" in out


def test_tidy_merges_near_copies_and_stays_merged(reg, tmp_path):
    import numpy as np

    reg.items["well"].source = reg.items["pot"].source = "openclipart x"
    reg.items["well"].description = "kept, it has words"

    class Vectors:
        ids = ["well", "pot"]  # noqa: RUF012
        image = np.array([[1.0, 0.0], [0.99, 0.14]])

    assert tidy(reg, Vectors())["merged"] == 1
    assert "pot" not in reg.items
    reg.add(Item(id="pot", name="clay pot"), "<svg/>")
    assert "pot" not in Registry(tmp_path).items


def test_a_shade_with_no_colour_set_is_the_colour_it_was():
    import re

    out, _ = recolorable('<path fill="#8B5A2B"/><path fill="#8B5A2B"/><path fill="#56381b"/><path fill="#c9a06c"/>')
    for fallback, pct, mix in re.findall(r"var\(--c1,#(\w{6})\) ([\d.]+)%,(black|white)", out):
        p, c = float(pct) / 100, [int(fallback[i : i + 2], 16) for i in (0, 2, 4)]
        got = [round(v * p + (255 if mix == "white" else 0) * (1 - p)) for v in c]
        assert any(all(abs(g - t) <= 3 for g, t in zip(got, want, strict=True)) for want in ([0x56, 0x38, 0x1b], [0xc9, 0xa0, 0x6c]))


def test_a_refused_item_stays_out_of_a_reseed(tmp_path):
    reg = Registry(tmp_path)
    item = Item(id="oc-bad", name="bad", height_cm=100, drawn_cm=100, source="openclipart", license="CC0")
    reg.add(item, '<path fill="#000"/>')
    reg.refuse("oc-bad")
    reg.add(item, '<path fill="#000"/>')
    assert "oc-bad" not in reg.items


def test_a_label_on_a_merged_item_counts_as_what_it_became():
    from vector_director.m2_retrieval.metrics import first_right, resolve

    assert resolve(["a", "x", "gone"], {"a": "b", "b": "c", "gone": None}) == {"c", "x", "gone"}
    assert first_right(["p", "c"], {"c"}) == 2
    assert first_right(["p"], {"c"}) is None
