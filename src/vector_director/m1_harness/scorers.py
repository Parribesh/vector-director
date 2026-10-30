"""Automatic scores. These become rewards in M6, so keep them cheap and deterministic."""

from __future__ import annotations

import itertools
import re
import xml.etree.ElementTree as ET

import numpy as np

from vector_director.core import Sample, Scores

# Anything that would run code or fetch from elsewhere when the SVG is opened.
_UNSAFE = re.compile(
    r"<\s*(script|foreignObject|iframe|image)\b|\son\w+\s*=|(href|src)\s*=\s*\"(?!#)", re.IGNORECASE
)


def _arrays(sample: Sample) -> list[np.ndarray]:
    """Frames as float32 arrays in 0..1, H x W x 3."""
    if not sample.frames:
        return []
    return [np.asarray(im, dtype=np.float32)[..., :3] / 255.0 for im in sample.frames.images]


class ValidityScorer:
    """valid: 1.0 if the SVG parses and renders non-blank frames, else 0.0.

    Also reports `parses`, `renders`, `nonblank` and `safe` so a 0 says why.
    """

    name = "validity"

    def __init__(self, blank_std: float = 0.01) -> None:
        self.blank_std = blank_std

    def score(self, sample: Sample) -> Scores:
        svg = sample.result.svg
        try:
            root = ET.fromstring(svg)
            parses = root.tag.rsplit("}", 1)[-1] == "svg"
        except ET.ParseError:
            parses = False
        frames = _arrays(sample)
        renders = bool(frames)
        # Non-blank: at least one frame has visible variation in pixel values.
        nonblank = any(float(f.std()) > self.blank_std for f in frames)
        safe = not _UNSAFE.search(svg)
        valid = parses and renders and nonblank and safe
        return {
            "valid": float(valid),
            "parses": float(parses),
            "renders": float(renders),
            "nonblank": float(nonblank),
            "safe": float(safe),
        }


class MotionScorer:
    """motion: share of pixels that change between consecutive frames, averaged.

    `motion` (0..1) is the mean fraction of pixels whose colour changes by more than
    `threshold` from one frame to the next, so a small ball crossing a big canvas still
    registers. `motion_l1` is the raw mean absolute difference. `moving_frac` is the
    share of frame pairs that differ at all, which separates "moves the whole time"
    from "one jump". Watch for flicker hacks: high motion with low clip is noise.
    """

    name = "motion"

    def __init__(self, threshold: float = 0.05, eps: float = 1e-3) -> None:
        self.threshold, self.eps = threshold, eps

    def score(self, sample: Sample) -> Scores:
        frames = _arrays(sample)
        if len(frames) < 2:
            return {"motion": 0.0, "motion_l1": 0.0, "moving_frac": 0.0}
        changed, l1 = [], []
        for a, b in itertools.pairwise(frames):
            d = np.abs(b - a).max(axis=-1)
            changed.append(float((d > self.threshold).mean()))
            l1.append(float(d.mean()))
        return {
            "motion": float(np.mean(changed)),
            "motion_l1": float(np.mean(l1)),
            "moving_frac": float(np.mean([x > self.eps for x in l1])),
        }


class ClipScorer:
    """clip: mean CLIP cosine similarity between the prompt and sampled frames.

    Raw CLIP cosine for a good match sits around 0.25 to 0.35, so compare runs with
    each other rather than reading it as a percentage. Needs `.[m1]` (torch + open_clip).
    """

    name = "clip"

    def __init__(
        self,
        model: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
        n_frames: int = 4,
        device: str | None = None,
    ) -> None:
        self.model, self.pretrained = model, pretrained
        self.n_frames = n_frames
        self.device = device
        self._loaded = None

    def _load(self):
        if self._loaded is None:
            import open_clip
            import torch

            device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
            model, _, preprocess = open_clip.create_model_and_transforms(
                self.model, pretrained=self.pretrained, device=device
            )
            model.eval()
            tokenizer = open_clip.get_tokenizer(self.model)
            self._loaded = (torch, model, preprocess, tokenizer, device)
        return self._loaded

    def score(self, sample: Sample) -> Scores:
        if not sample.frames or not sample.frames.images:
            return {"clip": 0.0}
        torch, model, preprocess, tokenizer, device = self._load()
        images = sample.frames.images
        step = max(1, len(images) // self.n_frames)
        picked = images[::step][: self.n_frames]
        with torch.no_grad():
            img = model.encode_image(torch.stack([preprocess(im) for im in picked]).to(device))
            txt = model.encode_text(tokenizer([sample.prompt]).to(device))
            img = img / img.norm(dim=-1, keepdim=True)
            txt = txt / txt.norm(dim=-1, keepdim=True)
            sims = (img @ txt.T).squeeze(-1)
        return {"clip": float(sims.mean())}


class CriticScorer:
    """Adapts any Critic (M1 judge, M4 quality head, M7 critic) to the Scorer protocol."""

    def __init__(self, critic, name: str = "judge") -> None:
        self.critic, self.name = critic, name

    def score(self, sample: Sample) -> Scores:
        if not sample.frames:
            return {self.name: 0.0}
        value, feedback = self.critic.critique(sample)
        sample.result.meta[f"{self.name}_feedback"] = feedback
        return {self.name: value}
