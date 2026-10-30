"""CLIP embedder (W4). M4 replaces the weights with fine-tuned ones."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class ClipEmbedder:
    """Implements core.interfaces.Embedder with open_clip."""

    dim = 512

    def __init__(self, model: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k") -> None:
        self.model, self.pretrained = model, pretrained

    def embed_text(self, texts: Sequence[str]) -> Any:
        raise NotImplementedError

    def embed_images(self, images: Sequence[Any]) -> Any:
        raise NotImplementedError


def style_arithmetic(embedder: ClipEmbedder, base: str, minus: str, plus: str) -> Any:
    """'cat' - 'flat' + 'line art' as a query vector."""
    raise NotImplementedError
