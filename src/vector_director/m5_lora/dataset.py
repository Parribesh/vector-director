"""Build 3 to 5k (prompt, animated SVG) pairs: distill from a strong model, filter with M1."""

from __future__ import annotations

from pathlib import Path

from vector_director.core.interfaces import Generator


def distill(teacher: Generator, prompts: list[str], out: Path, min_scores: dict[str, float]) -> int:
    """Keep only pairs the M1 harness scores above `min_scores`. Returns rows written."""
    raise NotImplementedError
