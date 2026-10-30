"""Three ways to tokenize path data like 'M 10 20 C 30 40 ...'."""

from __future__ import annotations

from typing import Protocol


class PathTokenizer(Protocol):
    def encode(self, path_d: str) -> list[int]: ...

    def decode(self, ids: list[int]) -> str: ...

    @property
    def vocab_size(self) -> int: ...


class CommandTokenizer:
    """Commands and quantized coordinates as tokens (e.g. 'C', 'x:12', 'y:40')."""

    def __init__(self, grid: int = 128) -> None:
        self.grid = grid

    def encode(self, path_d: str) -> list[int]:
        raise NotImplementedError

    def decode(self, ids: list[int]) -> str:
        raise NotImplementedError


class BPEPathTokenizer:
    """Custom BPE trained on your corpus (Hugging Face tokenizers)."""


def compare_tokenizers(paths: list[str]) -> dict[str, float]:
    """Tokens per path for GPT-2, a LLaMA tokenizer, and the two above."""
    raise NotImplementedError
