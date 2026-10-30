"""Scaffold tests: contracts hold and every milestone module imports cleanly."""

import importlib
import pkgutil

import pytest
from pydantic import ValidationError

import vector_director
from vector_director.core import AnimationSpec, GenerationResult, Sample
from vector_director.core.interfaces import Generator, RewardFn, Scorer
from vector_director.m1_harness.harness import summarize
from vector_director.m2_retrieval.metrics import mrr, recall_at_k


def _spec(**overrides):
    data = {
        "prompt": "a ball bounces",
        "objects": [{"id": "ball", "svg": '<circle cx="50" cy="50" r="10"/>'}],
        "tracks": [
            {
                "target": "ball",
                "property": "translate",
                "keyframes": [{"t": 0, "value": [0, 0]}, {"t": 1, "value": [0, 100]}],
            }
        ],
    }
    data.update(overrides)
    return AnimationSpec.model_validate(data)


def test_all_modules_import():
    names = [m.name for m in pkgutil.walk_packages(vector_director.__path__, "vector_director.")]
    assert sum(n.count(".") == 1 and ".m" in n for n in names) == 8
    for name in names:
        importlib.import_module(name)


def test_spec_valid_and_roundtrips():
    spec = _spec()
    assert AnimationSpec.model_validate_json(spec.model_dump_json()) == spec


def test_spec_rejects_unknown_target():
    with pytest.raises(ValidationError):
        _spec(tracks=[{"target": "ghost", "property": "opacity", "keyframes": [{"t": 0, "value": 1}]}])


def test_spec_rejects_track_past_duration():
    with pytest.raises(ValidationError):
        _spec(duration=0.5)


def test_stubs_satisfy_protocols():
    from vector_director.m1_harness.generator import ApiSpecGenerator
    from vector_director.m1_harness.scorers import ClipScorer
    from vector_director.m5_lora.model import LoraGenerator
    from vector_director.m6_preference.rewards import WeightedReward

    assert isinstance(ApiSpecGenerator(), Generator)
    assert isinstance(LoraGenerator("base"), Generator)
    assert isinstance(ClipScorer(), Scorer)
    assert isinstance(WeightedReward(), RewardFn)


def test_summarize_means():
    r = GenerationResult(svg="<svg/>")
    samples = [Sample("a", r, scores={"valid": 1.0}), Sample("b", r, scores={"valid": 0.0})]
    assert summarize(samples) == {"valid": 0.5}


def test_retrieval_metrics():
    assert recall_at_k(["a", "b", "c"], {"b", "z"}, k=2) == 0.5
    assert mrr(["a", "b", "c"], {"c"}) == pytest.approx(1 / 3)
