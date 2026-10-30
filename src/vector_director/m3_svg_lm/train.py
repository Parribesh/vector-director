"""Shared training loop and the loss table across n-gram, FFN and transformer."""

from __future__ import annotations


def train(model, train_ids, val_ids, steps: int = 5000, lr: float = 3e-4) -> dict[str, float]:
    raise NotImplementedError
