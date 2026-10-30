"""The seams between milestones, as Protocols.

A milestone "plugs in" by providing a class that satisfies one of these. Swapping
the API generator (M1) for the LoRA model (M5) is then a one-line change, and the
same eval harness scores both.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Protocol, runtime_checkable

from vector_director.core.types import Frames, GenerationResult, Hit, Sample, Scores


@runtime_checkable
class Generator(Protocol):
    """Prompt (+ optional retrieved context) -> SVG. M1 API model, M3 mini GPT, M5 LoRA, M6 tuned."""

    name: str

    def generate(self, prompt: str, context: Sequence[Hit] = ()) -> GenerationResult: ...


@runtime_checkable
class StreamingGenerator(Generator, Protocol):
    """Generator that yields SVG text as it is written (M8 SSE streaming)."""

    def stream(self, prompt: str, context: Sequence[Hit] = ()) -> Iterator[str]: ...


@runtime_checkable
class Renderer(Protocol):
    """SVG -> frames. M1 builds it with Playwright or resvg."""

    def render(self, svg: str, fps: int = 12, duration: float | None = None) -> Frames: ...


@runtime_checkable
class Scorer(Protocol):
    """One metric family over a rendered sample. Returns name -> value."""

    name: str

    def score(self, sample: Sample) -> Scores: ...


@runtime_checkable
class Embedder(Protocol):
    """Text and images into one vector space. M2 uses CLIP, M4 fine-tunes it."""

    dim: int

    def embed_text(self, texts: Sequence[str]) -> Any: ...

    def embed_images(self, images: Sequence[Any]) -> Any: ...


@runtime_checkable
class Retriever(Protocol):
    """Query -> ranked hits. M2: BM25, vector, hybrid, HyDE, reranked."""

    def search(self, query: str, k: int = 10) -> list[Hit]: ...


@runtime_checkable
class Reranker(Protocol):
    def rerank(self, query: str, hits: Sequence[Hit], k: int = 10) -> list[Hit]: ...


@runtime_checkable
class Critic(Protocol):
    """Looks at a render and says what to fix. M1 LLM judge, M4 quality head, M7 vision critic."""

    def critique(self, sample: Sample) -> tuple[float, str]: ...


@runtime_checkable
class RewardFn(Protocol):
    """Scalar reward for RL (M6). Usually a weighted sum of Scorer outputs."""

    def __call__(self, prompt: str, svg: str) -> float: ...
