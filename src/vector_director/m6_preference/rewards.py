"""Programmatic rewards built from M1 (and M4) scorers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WeightedReward:
    """Implements core.interfaces.RewardFn. reward = sum(weight * score)."""

    weights: dict[str, float] = field(
        default_factory=lambda: {"valid": 1.0, "clip": 2.0, "motion": 0.5}
    )

    def __call__(self, prompt: str, svg: str) -> float:
        raise NotImplementedError("M6: render, score with M1 scorers, weight")
