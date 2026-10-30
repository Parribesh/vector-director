"""Retrieval metrics. Pure functions, easy to unit-test first."""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def resolve(ids: Iterable[str], merged: dict[str, str | None]) -> set[str]:
    """Labels name items as they were: one merged since counts as the item it became."""
    out = set()
    for i in ids:
        seen = set()
        while merged.get(i) and i not in seen:
            seen.add(i)
            i = merged[i]
        out.add(i)
    return out


def first_right(ranked: Sequence[str], relevant: set[str]) -> int | None:
    return next((n for n, doc_id in enumerate(ranked, start=1) if doc_id in relevant), None)


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def mrr(ranked: Sequence[str], relevant: set[str]) -> float:
    for i, doc_id in enumerate(ranked, start=1):
        if doc_id in relevant:
            return 1.0 / i
    return 0.0
