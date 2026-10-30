"""Tiny attention model, grown into a mini GPT (W6, W8). Written by hand, no nn.Transformer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GPTConfig:
    vocab_size: int
    block_size: int = 256
    n_layer: int = 4
    n_head: int = 4
    n_embd: int = 128
    dropout: float = 0.1


def build_model(cfg: GPTConfig):
    """TODO(M3): attention head -> multi-head -> block (LayerNorm, FFN) -> GPT."""
    raise NotImplementedError


def attention_heatmap(model, ids: list[int]):
    """Return per-head attention maps to overlay on the strokes."""
    raise NotImplementedError
