"""LLM-as-judge over rendered frames (a vision model grades the animation)."""

from __future__ import annotations

from vector_director.core import Sample


class VisionJudge:
    """Implements core.interfaces.Critic. Returns (score 0..1, feedback text)."""

    rubric = "Does it match the prompt? Is the motion meaningful? Is it clean?"

    def critique(self, sample: Sample) -> tuple[float, str]:
        raise NotImplementedError("M1: send a frame strip to a vision model with a rubric")
