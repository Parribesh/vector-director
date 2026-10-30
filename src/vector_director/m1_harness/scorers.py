"""Automatic scores. These become rewards in M6, so keep them cheap and deterministic."""

from __future__ import annotations

from vector_director.core import Sample, Scores


class ValidityScorer:
    """valid: 1.0 if the SVG parses and renders non-blank frames, else 0.0."""

    name = "validity"

    def score(self, sample: Sample) -> Scores:
        raise NotImplementedError("M1: XML parse + non-blank render check")


class ClipScorer:
    """clip: mean CLIP cosine similarity between the prompt and sampled frames."""

    name = "clip"

    def __init__(self, model: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k") -> None:
        self.model, self.pretrained = model, pretrained

    def score(self, sample: Sample) -> Scores:
        raise NotImplementedError("M1: open_clip text-image similarity")


class MotionScorer:
    """motion: mean frame-to-frame pixel difference; 0 means nothing moves."""

    name = "motion"

    def score(self, sample: Sample) -> Scores:
        raise NotImplementedError("M1: frame difference")
