# M1: Spec, generator and eval harness

Bootcamp weeks: W1 to W3. Status: **stub**.

**Goal.** Turn a prompt into a typed `AnimationSpec`, compile it to SVG, render it headlessly, and score it automatically.

**Provides.** `ApiSpecGenerator` (Generator), `PlaywrightRenderer` (Renderer), `ValidityScorer` / `ClipScorer` / `MotionScorer` (Scorer), `VisionJudge` (Critic)

**Done when.** `vd eval --generator api-spec` prints a scoreboard (valid, clip, motion, judge) over a 50-prompt synthetic set.

**Files**

- `generator.py`
- `render.py`
- `scorers.py`
- `judge.py`
- `prompts.py`
- `harness.py`

**Install.** `uv pip install -e ".[m1]"`

All functions raise `NotImplementedError` until this milestone is built. Contracts live in
`vector_director/core`; do not change them without updating `docs/DESIGN.md`.
