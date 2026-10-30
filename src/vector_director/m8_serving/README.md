# M8: Ship it

Bootcamp weeks: W12, W13. Status: **stub**.

**Goal.** Grammar-constrained decoding, vLLM on Modal, and SSE streaming into the canvas.

**Provides.** `ConstrainedGenerator` (Generator), `create_app` (FastAPI), `modal_app`

**Done when.** a public demo link with p50 latency and cost per scene.

**Files**

- `constrained.py`
- `server.py`
- `modal_app.py`

**Install.** `uv pip install -e ".[m8]"`

All functions raise `NotImplementedError` until this milestone is built. Contracts live in
`vector_director/core`; do not change them without updating `docs/DESIGN.md`.
