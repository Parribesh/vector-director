"""The scoreboard: run any Generator over a prompt set and score every output.

This is the one function every later milestone calls to prove it helped.
"""

from __future__ import annotations

from collections.abc import Sequence

from vector_director.core import Sample, Scores
from vector_director.core.interfaces import Generator, Renderer, Retriever, Scorer


def evaluate(
    generator: Generator,
    prompts: Sequence[str],
    renderer: Renderer,
    scorers: Sequence[Scorer],
    retriever: Retriever | None = None,
) -> list[Sample]:
    """Generate, render and score each prompt. Retrieval is optional (M2 turns it on)."""
    samples: list[Sample] = []
    for prompt in prompts:
        context = retriever.search(prompt) if retriever else ()
        result = generator.generate(prompt, context)
        sample = Sample(prompt=prompt, result=result)
        try:
            sample.frames = renderer.render(result.svg)
        except Exception as exc:  # noqa: BLE001 - a broken SVG is a score, not a crash
            sample.result.meta["render_error"] = repr(exc)
        for scorer in scorers:
            sample.scores.update(scorer.score(sample))
        samples.append(sample)
    return samples


def summarize(samples: Sequence[Sample]) -> Scores:
    """Mean of every metric across samples."""
    keys = {k for s in samples for k in s.scores}
    return {k: sum(s.scores.get(k, 0.0) for s in samples) / len(samples) for k in sorted(keys)}
