# Vector Director

Type "a paper plane loops around and lands on a sleepy cat" and get an animated SVG back.
A small AI crew retrieves parts, draws the SVG, animates it, critiques its own render and fixes it.

This is a learning project: every feature is one technique from the
[newline AI Bootcamp](https://www.newline.co/courses/ai-bootcamp), built one milestone at a time,
and every milestone ends in a demo GIF and an eval number.

## Milestones

| # | Module | What you build | Bootcamp weeks | Status |
|---|--------|----------------|----------------|--------|
| M1 | [`m1_harness`](src/vector_director/m1_harness) | Typed spec, API generator, headless render, scorers, LLM judge | W1 to 3 | built |
| M2 | [`m2_retrieval`](src/vector_director/m2_retrieval) | SVG library, CLIP text/sketch search, hybrid RAG, HyDE, reranking | W4, W8 | stub |
| M3 | [`m3_svg_lm`](src/vector_director/m3_svg_lm) | Path tokenizers, trigram doodler, attention, mini GPT | W3, W5, W6, W8 | stub |
| M4 | [`m4_embeddings`](src/vector_director/m4_embeddings) | Triplet-loss motion embeddings, CLIP style and quality heads | W5, W7 | stub |
| M5 | [`m5_lora`](src/vector_director/m5_lora) | Distilled dataset, LoRA on a ~1.5B code model | W6 | stub |
| M6 | [`m6_preference`](src/vector_director/m6_preference) | Tool calls mid-generation, DPO, GRPO | W9, W10 | stub |
| M7 | [`m7_agents`](src/vector_director/m7_agents) | LangGraph director crew, beat sync, code index | W10, W11 | stub |
| M8 | [`m8_serving`](src/vector_director/m8_serving) | Constrained decoding, vLLM on Modal, SSE streaming | W12, W13 | stub |

M1 comes first: every later milestone proves itself on the M1 scoreboard.
Design and the rules between modules are in [docs/DESIGN.md](docs/DESIGN.md).

## Layout

```
src/vector_director/
  core/            shared contracts: AnimationSpec, data types, Protocols
  m1_harness/ ...  one package per milestone, each with its own README
  cli.py           `vd` command
tests/             contract tests (run on every change)
data/              raw/, processed/, eval/  (large files are git-ignored)
experiments/       run outputs, GIFs, scoreboards (git-ignored)
docs/DESIGN.md     architecture and module contracts
```

## Getting started

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"        # core only: pydantic
uv pip install -e ".[m1]"         # add a milestone's heavy deps when you start it
pytest                            # contract tests
vd milestones                     # list modules
vd schema                         # AnimationSpec JSON schema
```

## Working on a milestone

1. Branch `mN-short-name`, install `.[mN]`.
2. Replace the `NotImplementedError` stubs in that module only. Keep `core` contracts stable;
   if one must change, update `docs/DESIGN.md` in the same PR.
3. Add tests next to the existing ones and a scoreboard or GIF under `experiments/`.
4. Flip the status in the table above.
