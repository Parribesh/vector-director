"""Grammar-constrained decoding so every output parses (Outlines or XGrammar)."""

from __future__ import annotations

from vector_director.core import AnimationSpec


def spec_json_schema() -> dict:
    """The schema the decoder is constrained to. Already real: comes from core."""
    return AnimationSpec.model_json_schema()


class ConstrainedGenerator:
    """Wraps a model so it can only emit valid AnimationSpec JSON."""

    name = "constrained"

    def generate(self, prompt, context=()):
        raise NotImplementedError
