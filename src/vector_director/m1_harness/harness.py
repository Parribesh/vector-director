"""The scoreboard: run any Generator over a prompt set and score every output.

This is the one function every later milestone calls to prove it helped.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path

from vector_director.core import GenerationResult, Sample, Scores
from vector_director.core.interfaces import Generator, Renderer, Retriever, Scorer


def evaluate(
    generator: Generator,
    prompts: Sequence[str],
    renderer: Renderer,
    scorers: Sequence[Scorer],
    retriever: Retriever | None = None,
    on_sample: Callable[[int, Sample], None] | None = None,
) -> list[Sample]:
    """Generate, render and score each prompt. Retrieval is optional (M2 turns it on)."""
    samples: list[Sample] = []
    for i, prompt in enumerate(prompts):
        context = retriever.search(prompt) if retriever else ()
        try:
            result = generator.generate(prompt, context)
        except Exception as exc:  # noqa: BLE001 - one bad API call should not end the run
            result = GenerationResult(svg="", meta={"error": repr(exc)})
        sample = Sample(prompt=prompt, result=result)
        if result.svg:
            try:
                sample.frames = renderer.render(result.svg)
            except Exception as exc:  # noqa: BLE001 - a broken SVG is a score, not a crash
                sample.result.meta["render_error"] = repr(exc)
        for scorer in scorers:
            try:
                sample.scores.update(scorer.score(sample))
            except Exception as exc:  # noqa: BLE001
                sample.result.meta[f"{scorer.name}_error"] = repr(exc)
        samples.append(sample)
        if on_sample:
            on_sample(i, sample)
    return samples


def summarize(samples: Sequence[Sample]) -> Scores:
    """Mean of every metric across samples."""
    keys = {k for s in samples for k in s.scores}
    return {k: sum(s.scores.get(k, 0.0) for s in samples) / len(samples) for k in sorted(keys)}


def _slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n]


def save_run(samples: Sequence[Sample], out_dir: Path, meta: dict | None = None) -> Path:
    """Write a run to disk: scoreboard.json, samples.jsonl, and per sample an .svg and a .gif.

    Returns the scoreboard path. GIFs are what you look at; the JSON is what you diff.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, s in enumerate(samples):
        stem = f"{i:03d}-{_slug(s.prompt)}"
        if s.result.svg:
            (out_dir / f"{stem}.svg").write_text(s.result.svg)
        if s.frames and s.frames.images:
            first, *rest = s.frames.images
            first.save(
                out_dir / f"{stem}.gif",
                save_all=True,
                append_images=rest,
                duration=round(1000 / s.frames.fps),
                loop=0,
            )
        meta_row = {k: v for k, v in s.result.meta.items() if _jsonable(v)}
        rows.append({"id": stem, "prompt": s.prompt, "scores": s.scores, "meta": meta_row})
    with (out_dir / "samples.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    board = {"n": len(samples), "summary": summarize(samples) if samples else {}, **(meta or {})}
    cost = sum(
        s.result.meta.get("cost_usd", 0.0) + s.result.meta.get("judge_cost_usd", 0.0)
        for s in samples
    )
    if cost:
        board["cost_usd"] = round(cost, 4)
    path = out_dir / "scoreboard.json"
    path.write_text(json.dumps(board, indent=2) + "\n")
    return path


def _jsonable(value: object) -> bool:
    try:
        json.dumps(value)
        return True
    except TypeError:
        return False


def format_scoreboard(summary: Scores, title: str = "") -> str:
    """The summary as a small aligned table for the terminal."""
    width = max((len(k) for k in summary), default=6)
    lines = [title] if title else []
    lines += [f"  {k:<{width}}  {v:7.3f}" for k, v in summary.items()]
    return "\n".join(lines)
