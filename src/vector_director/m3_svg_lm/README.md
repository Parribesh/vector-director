# M3: SVG language models from scratch

Bootcamp weeks: W3, W5, W6, W8. Status: **stub**.

**Goal.** Tokenize path data three ways, then climb from a trigram doodler to a hand-written mini GPT.

**Provides.** `PathTokenizer`, `NGramModel`, `GPTConfig` / `build_model`; the trained model can later be wrapped as a Generator

**Done when.** a loss table across n-gram, FFN and transformer, plus a gallery of generated doodles.

**Files**

- `tokenizers.py`
- `ngram.py`
- `transformer.py`
- `train.py`

**Install.** `uv pip install -e ".[m3]"`

All functions raise `NotImplementedError` until this milestone is built. Contracts live in
`vector_director/core`; do not change them without updating `docs/DESIGN.md`.
