"""Synthetic prompt sets for evaluation (W2: synthetic data)."""

from __future__ import annotations

from pathlib import Path


def make_prompt_set(n: int = 50, seed: int = 0) -> list[str]:
    """TODO(M1): combine subjects x motions x styles, then let an LLM paraphrase."""
    raise NotImplementedError


def load_prompt_set(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]
