"""LoRA / QLoRA fine-tune with Hugging Face PEFT."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LoraConfig:
    base_model: str = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    r: int = 16
    alpha: int = 32
    dropout: float = 0.05
    target_modules: list[str] = field(default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj"])
    load_in_4bit: bool = False
    epochs: int = 2
    lr: float = 2e-4


def train(cfg: LoraConfig, dataset_path: str, out_dir: str) -> str:
    """Returns the adapter path. Run on Modal or Colab (single 24 GB GPU)."""
    raise NotImplementedError
