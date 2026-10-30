"""LangGraph crew: planner -> illustrator -> animator -> critic, with a retry loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from vector_director.core import AnimationSpec


@dataclass
class DirectorState:
    prompt: str
    plan: list[str] = field(default_factory=list)  # shot list / objects to draw
    spec: AnimationSpec | None = None
    svg: str | None = None
    critique: str | None = None
    score: float = 0.0
    attempts: int = 0


def build_graph(planner, illustrator, animator, critic, max_attempts: int = 3):
    """TODO(M7): nodes for each role; edge critic -> animator while score < threshold."""
    raise NotImplementedError
