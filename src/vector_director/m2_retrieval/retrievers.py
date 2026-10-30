"""Retrievers, simplest first. Each one implements core.interfaces.Retriever."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from vector_director.core import Hit
from vector_director.m2_retrieval.library import Registry

TOKEN = re.compile(r"[a-z0-9]+|[^\W\d_]+", re.IGNORECASE)


def tokens(text: str) -> list[str]:
    return [t.lower().rstrip("s") if len(t) > 3 else t.lower() for t in TOKEN.findall(text)]


def _hit(reg: Registry, item_id: str, score: float) -> Hit:
    it = reg.items[item_id]
    return Hit(id=item_id, score=float(score), text=it.text(), meta={"name": it.name, "kind": it.kind, "status": it.status, "height_cm": it.height_cm})


def _allowed(reg: Registry, kind: str | None, status: str | None) -> Callable[[str], bool]:
    def ok(item_id: str) -> bool:
        it = reg.items.get(item_id)
        return bool(it) and (not kind or it.kind == kind) and (not status or it.status == status)

    return ok


class BM25Retriever:
    """Keyword search over names, tags and descriptions."""

    def __init__(self, reg: Registry, k1: float = 1.5, b: float = 0.75) -> None:
        self.reg, self.k1, self.b = reg, k1, b
        self.refresh()

    def refresh(self) -> None:
        self.docs = {i: Counter(tokens(it.text())) for i, it in self.reg.items.items()}
        self.avg = sum(sum(c.values()) for c in self.docs.values()) / max(1, len(self.docs))
        self.df = Counter(t for c in self.docs.values() for t in c)

    def search(self, query: str, k: int = 10, kind: str | None = None, status: str | None = None) -> list[Hit]:
        ok, n, out = _allowed(self.reg, kind, status), len(self.docs), []
        for item_id, c in self.docs.items():
            if not ok(item_id):
                continue
            length, score = sum(c.values()), 0.0
            for t in tokens(query):
                if t in c:
                    idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    score += idf * c[t] * (self.k1 + 1) / (c[t] + self.k1 * (1 - self.b + self.b * length / self.avg))
            if score > 0:
                out.append((score, item_id))
        return [_hit(self.reg, i, s) for s, i in sorted(out, reverse=True)[:k]]


class VectorRetriever:
    """CLIP text query against each item's picture and its words."""

    def __init__(self, reg: Registry, embedder, image_weight: float = 0.6) -> None:
        self.reg, self.embedder, self.image_weight = reg, embedder, image_weight
        self.path = Path(reg.root) / "vectors.npz"
        self.load()

    def load(self) -> None:
        import numpy as np

        if self.path.exists():
            d = np.load(self.path, allow_pickle=False)
            self.ids, self.image, self.text = list(d["ids"]), d["image"], d["text"]
        else:
            self.ids, self.image, self.text = [], None, None

    def build(self) -> int:
        """Embed every item's thumbnail and text."""
        from PIL import Image

        self.ids = [i for i in self.reg.items if self.reg.thumb_path(i).exists()]
        self.image = self.embedder.embed_images([Image.open(self.reg.thumb_path(i)).convert("RGB") for i in self.ids])
        self.text = self.embedder.embed_text([self.reg.items[i].text() for i in self.ids])
        self.save()
        return len(self.ids)

    def save(self) -> None:
        import numpy as np

        np.savez(self.path, ids=np.array(self.ids), image=self.image, text=self.text)

    def refresh_text(self, item_id: str) -> None:
        """After an edit: new words, same picture."""
        if item_id in self.ids:
            self.text[self.ids.index(item_id)] = self.embedder.embed_text([self.reg.items[item_id].text()])[0]
            self.save()

    def _rank(self, sims, k: int, kind: str | None, status: str | None) -> list[Hit]:
        import numpy as np

        ok, out = _allowed(self.reg, kind, status), []
        for j in np.argsort(-sims):
            if ok(self.ids[j]):
                out.append(_hit(self.reg, self.ids[j], sims[j]))
                if len(out) == k:
                    break
        return out

    def search(self, query: str, k: int = 10, kind: str | None = None, status: str | None = None) -> list[Hit]:
        if not self.ids:
            return []
        q = self.embedder.embed_text([query])[0]
        return self._rank(self.image_weight * (self.image @ q) + (1 - self.image_weight) * (self.text @ q), k, kind, status)

    def search_image(self, image, k: int = 10, kind: str | None = None, status: str | None = None) -> list[Hit]:
        return self._rank(self.image @ self.embedder.embed_images([image])[0], k, kind, status)


class HybridRetriever:
    """Reciprocal rank fusion of BM25 and vector results."""

    def __init__(self, retrievers: Sequence, weights: Sequence[float] | None = None, c: int = 60, depth: int = 50) -> None:
        self.retrievers, self.weights, self.c, self.depth = retrievers, weights or [1.0] * len(retrievers), c, depth

    def search(self, query: str, k: int = 10, kind: str | None = None, status: str | None = None) -> list[Hit]:
        scores: dict[str, float] = {}
        hits: dict[str, Hit] = {}
        for r, w in zip(self.retrievers, self.weights, strict=True):
            for rank, h in enumerate(r.search(query, k=self.depth, kind=kind, status=status), start=1):
                scores[h.id] = scores.get(h.id, 0.0) + w / (self.c + rank)
                hits.setdefault(h.id, h)
        best = sorted(scores, key=lambda i: -scores[i])[:k]
        return [Hit(id=i, score=scores[i], text=hits[i].text, meta=hits[i].meta) for i in best]


class HyDERetriever:
    """Generate a hypothetical description first, then search with it."""

    def __init__(self, base, write: Callable[[str], str]) -> None:
        self.base, self.write = base, write

    def search(self, query: str, k: int = 10, **kw) -> list[Hit]:
        return self.base.search(self.write(query), k=k, **kw)


class CrossEncoderReranker:
    """Implements core.interfaces.Reranker."""

    def rerank(self, query: str, hits: Sequence[Hit], k: int = 10) -> list[Hit]:
        raise NotImplementedError("M2: a later step, once the labeled set shows ranking is what's weak")
