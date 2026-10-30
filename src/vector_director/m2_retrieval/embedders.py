"""CLIP embedder (W4). M4 replaces the weights with fine-tuned ones."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class ClipEmbedder:
    """Implements core.interfaces.Embedder with open_clip. Vectors come back L2-normalised."""

    dim = 512

    def __init__(self, model: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k", device: str | None = None, batch: int = 64) -> None:
        self.model, self.pretrained, self.device, self.batch = model, pretrained, device, batch
        self._loaded = None

    def _load(self):
        if self._loaded is None:
            import open_clip
            import torch

            device = self.device or ("mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu")
            model, _, preprocess = open_clip.create_model_and_transforms(self.model, pretrained=self.pretrained, device=device)
            model.eval()
            self._loaded = (torch, model, preprocess, open_clip.get_tokenizer(self.model), device)
        return self._loaded

    def embed_text(self, texts: Sequence[str]) -> Any:
        import numpy as np

        torch, model, _, tokenizer, device = self._load()
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), self.batch):
                v = model.encode_text(tokenizer(list(texts[i : i + self.batch])).to(device))
                out.append((v / v.norm(dim=-1, keepdim=True)).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, self.dim), dtype="float32")

    def embed_images(self, images: Sequence[Any]) -> Any:
        import numpy as np

        torch, model, preprocess, _, device = self._load()
        out = []
        with torch.no_grad():
            for i in range(0, len(images), self.batch):
                v = model.encode_image(torch.stack([preprocess(im) for im in images[i : i + self.batch]]).to(device))
                out.append((v / v.norm(dim=-1, keepdim=True)).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, self.dim), dtype="float32")


def style_arithmetic(embedder: ClipEmbedder, base: str, minus: str, plus: str) -> Any:
    """'cat' - 'flat' + 'line art' as a query vector."""
    v = embedder.embed_text([base, minus, plus])
    q = v[0] - v[1] + v[2]
    return q / ((q**2).sum() ** 0.5)
