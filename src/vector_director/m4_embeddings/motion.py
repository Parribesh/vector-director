"""Triplet-loss motion embeddings: 'bouncy' clips sit near each other."""

from __future__ import annotations


def make_triplets(specs, n: int):
    """Anchor/positive share a motion; hard negatives swap only the easing."""
    raise NotImplementedError


class MotionEncoder:
    """Frames (or keyframe tracks) -> motion vector. Trained with TripletMarginLoss."""

    def fit(self, triplets, epochs: int = 10) -> None:
        raise NotImplementedError

    def embed(self, frames) -> list[float]:
        raise NotImplementedError
