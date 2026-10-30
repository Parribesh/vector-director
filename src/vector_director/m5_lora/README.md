# M5: LoRA animator model

Bootcamp weeks: W6. Status: **stub**.

**Goal.** Distill 3 to 5k prompt-to-animated-SVG pairs (filtered by M1) and LoRA-tune a ~1.5B code model.

**Provides.** `distill`, `LoraConfig` / `train`, `LoraGenerator` (Generator)

**Done when.** the LoRA model beats its base model on the M1 scoreboard, and you know where it loses to the API model.

**Files**

- `dataset.py`
- `train.py`
- `model.py`

**Install.** `uv pip install -e ".[m5]"`

All functions raise `NotImplementedError` until this milestone is built. Contracts live in
`vector_director/core`; do not change them without updating `docs/DESIGN.md`.
