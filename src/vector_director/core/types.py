"""Plain data passed between modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vector_director.core.spec import AnimationSpec

Scores = dict[str, float]
"""Metric name -> value, e.g. {"valid": 1.0, "clip": 0.31, "motion": 0.12}."""


@dataclass
class GenerationResult:
    svg: str
    spec: AnimationSpec | None = None
    meta: dict[str, Any] = field(default_factory=dict)  # model, latency_ms, tokens, cost, trace id...


@dataclass
class Frames:
    """Rendered frames of one animation. `images` are PIL images or numpy arrays."""

    images: list[Any]
    fps: int
    width: int
    height: int


@dataclass
class Sample:
    """One evaluated row: what was asked, what came out, how it scored."""

    prompt: str
    result: GenerationResult
    frames: Frames | None = None
    scores: Scores = field(default_factory=dict)


@dataclass
class Hit:
    """One retrieval result."""

    id: str
    score: float
    svg: str | None = None
    text: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
