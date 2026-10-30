"""`vd` command line. Subcommands come online milestone by milestone."""

from __future__ import annotations

import argparse
import json

MILESTONES = {
    "m1_harness": "Spec, generator and eval harness",
    "m2_retrieval": "Asset library with CLIP search and RAG",
    "m3_svg_lm": "SVG language models from scratch",
    "m4_embeddings": "Embeddings for style and motion",
    "m5_lora": "LoRA animator model",
    "m6_preference": "Self-correcting and preference-tuned",
    "m7_agents": "Director agents and music sync",
    "m8_serving": "Ship it",
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="vd", description="Vector Director")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("milestones", help="list milestones")
    sub.add_parser("schema", help="print the AnimationSpec JSON schema")
    ev = sub.add_parser("eval", help="(M1) score a generator over a prompt set")
    ev.add_argument("--generator", default="api-spec", choices=["api-spec", "baseline"])
    providers = ["anthropic", "gemini", "ollama"]
    ev.add_argument("--provider", default="anthropic", choices=providers, help="for api-spec")
    ev.add_argument("--model", default=None, help="model id (default: the provider's default)")
    ev.add_argument("--effort", default=None, choices=["low", "medium", "high", "xhigh", "max"])
    ev.add_argument("--prompts", default="data/eval/prompts.txt")
    ev.add_argument("--limit", type=int, default=None, help="only the first N prompts")
    ev.add_argument("--fps", type=int, default=12)
    ev.add_argument("--no-clip", action="store_true", help="skip CLIP (no torch needed)")
    ev.add_argument("--judge", action="store_true", help="add the vision LLM judge (API cost)")
    ev.add_argument("--judge-provider", default=None, choices=providers, help="default: --provider")
    ev.add_argument("--judge-model", default=None)
    ev.add_argument("--out", default=None, help="run dir (default experiments/m1/<name>)")
    pp = sub.add_parser("prop", help="(M1) draw one prop for a stage, with its real size")
    pp.add_argument("prompt")
    pp.add_argument("--slug", required=True, help="file name and id prefix")
    pp.add_argument("--height-cm", type=float, required=True)
    pp.add_argument("--provider", default="gemini", choices=providers)
    pp.add_argument("--model", default=None)
    pp.add_argument("--out", default=".")
    st = sub.add_parser("set", help="(M1) paint one location for a stage")
    st.add_argument("prompt")
    st.add_argument("--slug", required=True, help="file name and id prefix")
    st.add_argument("--kind", default="outdoor", choices=["outdoor", "interior"])
    st.add_argument("--provider", default="gemini", choices=providers)
    st.add_argument("--model", default=None)
    st.add_argument("--out", default=".")
    pr = sub.add_parser("prompts", help="(M1) write the synthetic eval prompt set")
    pr.add_argument("--n", type=int, default=50)
    pr.add_argument("--seed", type=int, default=0)
    pr.add_argument("--out", default="data/eval/prompts.txt")
    args = parser.parse_args(argv)

    if args.cmd == "milestones":
        for mod, title in MILESTONES.items():
            print(f"{mod:16} {title}")
    elif args.cmd == "schema":
        from vector_director.core import AnimationSpec

        print(json.dumps(AnimationSpec.model_json_schema(), indent=2))
    elif args.cmd == "prompts":
        from pathlib import Path

        from vector_director.m1_harness.prompts import make_prompt_set, save_prompt_set

        save_prompt_set(make_prompt_set(args.n, args.seed), Path(args.out))
        print(f"wrote {args.n} prompts to {args.out}")
    elif args.cmd == "eval":
        _eval(args)
    elif args.cmd == "prop":
        _prop(args)
    elif args.cmd == "set":
        _set(args)


def _prop(args: argparse.Namespace) -> None:
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from vector_director.m1_harness.llm import make_llm
    from vector_director.m1_harness.prop import make_prop

    llm = make_llm(args.provider, args.model)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        prop = make_prop(args.prompt, args.slug, args.height_cm, llm, browser.new_page())
        browser.close()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{prop.slug}.svg").write_text(prop.svg)
    (out / f"{prop.slug}.png").write_bytes(prop.png)
    (out / f"{prop.slug}.json").write_text(json.dumps(prop.meta, indent=2, ensure_ascii=False))
    print(
        json.dumps(
            {"slug": prop.slug, "svg": str(out / f"{prop.slug}.svg"), **prop.meta},
            ensure_ascii=False,
        )
    )


def _set(args: argparse.Namespace) -> None:
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from vector_director.m1_harness.llm import make_llm
    from vector_director.m1_harness.set_design import make_set

    llm = make_llm(args.provider, args.model)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        art = make_set(args.prompt, args.slug, args.kind, llm, browser.new_page())
        browser.close()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{art.slug}.svg").write_text(art.svg)
    (out / f"{art.slug}.png").write_bytes(art.png)
    print(
        json.dumps(
            {"slug": art.slug, "svg": str(out / f"{art.slug}.svg"), **art.meta}, ensure_ascii=False
        )
    )


def _eval(args: argparse.Namespace) -> None:
    import time
    from pathlib import Path

    from vector_director.m1_harness import generator as gen
    from vector_director.m1_harness.harness import evaluate, format_scoreboard, save_run
    from vector_director.m1_harness.prompts import load_prompt_set, make_prompt_set
    from vector_director.m1_harness.render import PlaywrightRenderer
    from vector_director.m1_harness.scorers import (
        ClipScorer,
        CriticScorer,
        MotionScorer,
        ValidityScorer,
    )

    path = Path(args.prompts)
    prompts = load_prompt_set(path) if path.exists() else make_prompt_set()
    prompts = prompts[: args.limit] if args.limit else prompts
    if args.generator == "api-spec":
        generator = gen.ApiSpecGenerator(
            provider=args.provider, model=args.model, effort=args.effort
        )
        run_name = f"{generator.name}-{generator.llm.model.replace(':', '-')}"
    else:
        generator = gen.BaselineGenerator()
        run_name = generator.name
    scorers = [ValidityScorer(), MotionScorer()]
    if not args.no_clip:
        scorers.append(ClipScorer())
    if args.judge:
        from vector_director.m1_harness.judge import VisionJudge

        judge = VisionJudge(provider=args.judge_provider or args.provider, model=args.judge_model)
        scorers.append(CriticScorer(judge))
    out = Path(args.out or f"experiments/m1/{time.strftime('%Y%m%d-%H%M%S')}-{run_name}")

    def progress(i: int, sample) -> None:
        headline = ("valid", "motion", "clip", "judge")
        shown = " ".join(f"{k}={sample.scores[k]:.2f}" for k in headline if k in sample.scores)
        err = sample.result.meta.get("error") or sample.result.meta.get("render_error") or ""
        print(f"[{i + 1}/{len(prompts)}] {sample.prompt[:48]:48} {shown} {err[:60]}", flush=True)

    with PlaywrightRenderer(fps=args.fps) as renderer:
        samples = evaluate(generator, prompts, renderer, scorers, on_sample=progress)
    board = save_run(samples, out, meta={"generator": run_name, "prompts": str(path)})
    data = json.loads(board.read_text())
    print(format_scoreboard(data["summary"], title=f"\n{run_name} on {len(samples)} prompts"))
    if "cost_usd" in data:
        print(f"  cost_usd  {data['cost_usd']:.4f}")
    print(f"run saved to {out}")


if __name__ == "__main__":
    main()
