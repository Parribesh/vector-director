"""Synthetic prompt sets for evaluation (W2: synthetic data).

`make_prompt_set` crosses subjects x motions x settings from small hand-written lists,
so every prompt names something to draw and something it does. The lists are the
knobs: add to them when the scoreboard saturates. (Paraphrasing with an LLM is the
next step; it adds wording variety the generator should be robust to.)
"""

from __future__ import annotations

import random
from pathlib import Path

SUBJECTS = [
    "a red ball",
    "a paper plane",
    "a sleepy cat",
    "a hot air balloon",
    "a small rocket",
    "a yellow fish",
    "a windmill",
    "a bouncing frog",
    "a candle flame",
    "a sailboat",
    "a butterfly",
    "a spinning top",
    "a robot",
    "a raindrop",
    "a snail",
    "a kite",
    "a ladybug",
    "a bee",
    "a lighthouse",
    "a cup of coffee",
    "a pendulum clock",
    "a leaf",
]
MOTIONS = [
    "bounces three times",
    "loops around in a circle",
    "drifts slowly from left to right",
    "spins in place",
    "rises and falls gently",
    "zooms in and fades out",
    "wobbles",
    "flies across and lands",
    "pulses like a heartbeat",
    "sways back and forth",
    "changes colour from warm to cool",
    "shakes nervously",
    "slides in and stops",
]
SETTINGS = [
    "",
    "",
    "",  # most prompts have no setting
    "on a blue sky",
    "at night under the stars",
    "over green hills",
    "in the rain",
    "under the sea",
    "on a wooden table",
    "in a snowy field",
]


def make_prompt_set(n: int = 50, seed: int = 0) -> list[str]:
    """n distinct prompts, deterministic for a given seed."""
    combos = [(s, m, w) for s in SUBJECTS for m in MOTIONS for w in SETTINGS]
    rng = random.Random(seed)
    rng.shuffle(combos)
    prompts: list[str] = []
    for subject, motion, setting in combos:
        prompt = " ".join(p for p in (subject, motion, setting) if p)
        if prompt not in prompts:
            prompts.append(prompt)
        if len(prompts) == n:
            break
    return prompts


def load_prompt_set(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def save_prompt_set(prompts: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(prompts) + "\n")
