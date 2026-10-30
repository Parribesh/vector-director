"""The gallery without a browser or CLIP: registry edits, keyword search, fusion, licence filter."""

from __future__ import annotations

import pytest

from vector_director.core import Hit
from vector_director.m2_retrieval.library import Item, Registry, openmoji_entries
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
