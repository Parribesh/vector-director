# M6: Self-correcting and preference-tuned

Bootcamp weeks: W9, W10. Status: **stub**.

**Goal.** Let the model call render/validate tools mid-generation, then DPO and GRPO with rewards built from the M1 scorers.

**Provides.** `run_tool`, `WeightedReward` (RewardFn), `build_pairs` / `train_dpo`, `train_grpo`

**Done when.** valid-output rate and CLIP match rise over M5, with reward-hacking cases written down.

**Files**

- `tools.py`
- `rewards.py`
- `dpo.py`
- `grpo.py`

**Install.** `uv pip install -e ".[m6]"`

All functions raise `NotImplementedError` until this milestone is built. Contracts live in
`vector_director/core`; do not change them without updating `docs/DESIGN.md`.
