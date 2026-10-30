# M7: Director agents and music sync

Bootcamp weeks: W10, W11. Status: **stub**.

**Goal.** Planner, illustrator, animator and critic in LangGraph with a retry loop; beat-synced keyframes; an AST index of your own code.

**Provides.** `DirectorState`, `build_graph`, `beats_from_audio` / `snap_to_beats`, `index_repo`

**Done when.** a 10-second beat-synced scene from one prompt, plus agent traces.

**Files**

- `graph.py`
- `music.py`
- `code_index.py`

**Install.** `uv pip install -e ".[m7]"`

All functions raise `NotImplementedError` until this milestone is built. Contracts live in
`vector_director/core`; do not change them without updating `docs/DESIGN.md`.
