"""The fine-tuned model as a Generator, so the M1 harness can score it."""

from __future__ import annotations

from collections.abc import Sequence

from vector_director.core import GenerationResult, Hit


class LoraGenerator:
    """Implements core.interfaces.Generator."""

    name = "lora"

    def __init__(self, base_model: str, adapter_path: str | None = None) -> None:
        self.base_model, self.adapter_path = base_model, adapter_path

    def generate(self, prompt: str, context: Sequence[Hit] = ()) -> GenerationResult:
        raise NotImplementedError
