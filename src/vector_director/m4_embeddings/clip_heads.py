"""CLIP fine-tuning with task heads (W7)."""

from __future__ import annotations


class StyleClassifierHead:
    """CLIP image features -> icon style (flat, line, glyph, hand-drawn, ...)."""


class QualityRegressorHead:
    """CLIP image features -> 'looks good' score. Reused as a reward in M6.

    Should also implement core.interfaces.Scorer (name='quality').
    """

    name = "quality"

    def score(self, sample):
        raise NotImplementedError


def compare_zero_shot_vs_finetuned(eval_set) -> dict[str, float]:
    raise NotImplementedError
