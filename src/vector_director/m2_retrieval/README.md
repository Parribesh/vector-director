# M2: Asset library with CLIP search and RAG

Bootcamp weeks: W4, W8. Status: **stub**.

**Goal.** Index 2 to 5k open-license SVGs and animation docs; search by text or sketch; feed the best parts to the generator.

**Provides.** `ClipEmbedder` (Embedder), `BM25Retriever` / `VectorRetriever` / `HybridRetriever` / `HyDERetriever` (Retriever), `CrossEncoderReranker` (Reranker)

**Done when.** recall@10 and MRR on a labeled query set, and the M1 scoreboard improves with retrieval on.

**Files**

- `library.py`
- `embedders.py`
- `retrievers.py`
- `docs_index.py`
- `metrics.py`

**Install.** `uv pip install -e ".[m2]"`

All functions raise `NotImplementedError` until this milestone is built. Contracts live in
`vector_director/core`; do not change them without updating `docs/DESIGN.md`.
