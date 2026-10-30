# M4: Embeddings that understand style and motion

Bootcamp weeks: W5, W7. Status: **stub**.

**Goal.** Triplet-loss motion embeddings and CLIP fine-tuned with a style classifier and a quality regressor.

**Provides.** `MotionEncoder`, `StyleClassifierHead`, `QualityRegressorHead` (Scorer, reused as an M6 reward)

**Done when.** zero-shot vs fine-tuned accuracy, and the quality head plugged into the M1 scoreboard.

**Files**

- `motion.py`
- `clip_heads.py`

**Install.** `uv pip install -e ".[m4]"`

All functions raise `NotImplementedError` until this milestone is built. Contracts live in
`vector_director/core`; do not change them without updating `docs/DESIGN.md`.
