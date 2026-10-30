# M1: Spec, generator and eval harness

Bootcamp weeks: W1 to W3. Status: **built, awaiting first live run**.

**Goal.** Turn a prompt into a typed `AnimationSpec`, compile it to SVG, render it headlessly, and score it automatically.

**Provides.** `ApiSpecGenerator` / `BaselineGenerator` (Generator), `PlaywrightRenderer` (Renderer),
`ValidityScorer` / `MotionScorer` / `ClipScorer` / `CriticScorer` (Scorer), `VisionJudge` (Critic)

**Done when.** `vd eval --generator api-spec --judge` prints a scoreboard (valid, clip, motion, judge) over a 50-prompt synthetic set.

## Setup

```bash
uv pip install -e ".[m1,dev]"
playwright install chromium          # or point VD_CHROMIUM at an existing Chrome binary
vd prompts                           # writes data/eval/prompts.txt (50 prompts, seed 0)
```

Then pick a model provider. All three go through the same `llm.JsonLLM` seam:

| `--provider` | Needs | Default generator / judge model |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-opus-5-5` / `claude-opus-5-5` |
| `gemini` | `GEMINI_API_KEY` (free tier at aistudio.google.com/apikey) | `gemini-2.5-flash` / same |
| `ollama` | Ollama running locally, `ollama pull qwen2.5-coder:7b qwen2.5vl:7b` | `qwen2.5-coder:7b` / `qwen2.5vl:7b` |

## Run it

```bash
vd eval --generator baseline --no-clip                 # no model at all: the floor
vd eval --provider gemini --limit 5 --no-clip          # quick free smoke test
vd eval --provider ollama --judge                      # fully local
vd eval --provider anthropic --judge                   # full 50-prompt scoreboard
vd eval --provider gemini --judge-provider anthropic   # mix: free generator, strong judge
```

Each run writes `experiments/m1/<time>-<generator>/` with `scoreboard.json`, `samples.jsonl`
and one `.svg` + `.gif` per prompt. Look at the GIFs; diff the JSON.

## How it fits together

```
prompt ──> ApiSpecGenerator ──llm.ask(schema=AnimationSpec)──> JSON
             │  Pydantic validates; on error, sends spec + error back once (repair loop)
             ▼
        AnimationSpec ──compile.spec_to_svg──> SVG with CSS @keyframes
             ▼
   PlaywrightRenderer: headless Chromium, pause every animation at t = i/fps, screenshot
             ▼
   Frames ──> ValidityScorer (parses, renders, nonblank, safe)
          ──> MotionScorer   (share of pixels changing per frame)
          ──> ClipScorer     (prompt vs frames, open_clip ViT-B-32)
          ──> CriticScorer(VisionJudge)  (contact sheet -> rubric: match, motion, craft)
```

**Files**

- `compile.py`: spec to SVG. One nested `<g>` per transform layer so translate, rotate
  and scale never overwrite each other's CSS `transform`.
- `llm.py`: the provider seam (Claude SDK, Gemini REST, Ollama REST), all schema-constrained.
- `generator.py`: `ApiSpecGenerator` with the validate-and-repair loop; `BaselineGenerator`.
- `render.py`: Playwright renderer.
- `scorers.py`, `judge.py`: metrics and the vision judge.
- `prompts.py`: subjects x motions x settings synthetic prompt set.
- `harness.py`: `evaluate`, `summarize`, `save_run`.

## Experiments to try (the learning part)

1. Same prompts, three providers: where does each fail? (`valid` vs `clip` vs `judge`.)
2. Turn the repair loop off (`max_repairs=0`): how much does `valid` drop?
3. Judge vs CLIP: hand-rate 20 GIFs and check which metric agrees with you more.
4. Game the metrics: a flickering background maxes `motion`. Does `judge` catch it?
