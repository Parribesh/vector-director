"""Trigram 'doodler' over path tokens (W5)."""

from __future__ import annotations


class NGramModel:
    def __init__(self, n: int = 3, smoothing: float = 1.0) -> None:
        self.n, self.smoothing = n, smoothing

    def fit(self, sequences: list[list[int]]) -> None:
        raise NotImplementedError

    def sample(self, max_len: int = 64, temperature: float = 1.0) -> list[int]:
        raise NotImplementedError

    def perplexity(self, sequences: list[list[int]]) -> float:
        raise NotImplementedError
