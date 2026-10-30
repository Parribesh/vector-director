"""Prompt -> AnimationSpec -> SVG using an API model with structured output."""

from __future__ import annotations

from collections.abc import Sequence

from vector_director.core import AnimationSpec, GenerationResult, Hit


class ApiSpecGenerator:
    """Implements core.interfaces.Generator.

    TODO(M1): call an API model with Instructor/Pydantic so it returns an
    AnimationSpec, then compile it with `spec_to_svg`.
    """

    name = "api-spec"

    def __init__(self, model: str = "claude-sonnet-5-5") -> None:
        self.model = model

    def generate(self, prompt: str, context: Sequence[Hit] = ()) -> GenerationResult:
        raise NotImplementedError("M1: prompt -> AnimationSpec via structured output")


def spec_to_svg(spec: AnimationSpec) -> str:
    """Compile a spec into one self-contained animated SVG (CSS keyframes or SMIL).

    TODO(M1): pick the target format once we know what sadhu uses.
    """
    raise NotImplementedError("M1: compile AnimationSpec to SVG")
