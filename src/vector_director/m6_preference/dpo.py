"""DPO on pairs ranked by render scores (TRL DPOTrainer)."""

from __future__ import annotations


def build_pairs(generator, prompts: list[str], reward, n_per_prompt: int = 4):
    """Sample n outputs per prompt; chosen = best reward, rejected = worst."""
    raise NotImplementedError


def train_dpo(model_path: str, pairs, out_dir: str, beta: float = 0.1) -> str:
    raise NotImplementedError
