"""Retrievers, simplest first. Each one implements core.interfaces.Retriever."""

from __future__ import annotations

from collections.abc import Sequence

from vector_director.core import Hit


class BM25Retriever:
    """Keyword search over asset tags and doc chunks."""

    def search(self, query: str, k: int = 10) -> list[Hit]:
        raise NotImplementedError


class VectorRetriever:
    """CLIP text -> image search in LanceDB. Also accepts a sketch image (search_image)."""

    def search(self, query: str, k: int = 10) -> list[Hit]:
        raise NotImplementedError

    def search_image(self, image, k: int = 10) -> list[Hit]:
        raise NotImplementedError


class HybridRetriever:
    """Reciprocal rank fusion of BM25 and vector results."""

    def __init__(self, retrievers: Sequence, weights: Sequence[float] | None = None) -> None:
        self.retrievers, self.weights = retrievers, weights

    def search(self, query: str, k: int = 10) -> list[Hit]:
        raise NotImplementedError


class HyDERetriever:
    """Generate a hypothetical SVG/description first, then search with it."""

    def search(self, query: str, k: int = 10) -> list[Hit]:
        raise NotImplementedError


class CrossEncoderReranker:
    """Implements core.interfaces.Reranker."""

    def rerank(self, query: str, hits: Sequence[Hit], k: int = 10) -> list[Hit]:
        raise NotImplementedError
