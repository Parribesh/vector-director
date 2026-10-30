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
    lb = sub.add_parser("library", help="(M2) build the gallery")
    lb.add_argument("action", choices=["seed", "openmoji", "openclipart", "label", "thumbs", "embed", "eval"])
    lb.add_argument("--sadhu", default="../sadhu", help="seed: a sadhu checkout")
    lb.add_argument("--openmoji", default="data/raw/openmoji", help="openmoji: the unpacked download")
    lb.add_argument("--heights", default=None, help="openmoji: JSON of id -> height_cm")
    lb.add_argument("--labels", default="data/eval/retrieval.jsonl", help="eval: the labeled queries")
    lb.add_argument("--root", default="library")
    se = sub.add_parser("search", help="(M2) search the gallery")
    se.add_argument("query")
    se.add_argument("-k", type=int, default=10)
    se.add_argument("--kind", default=None)
    se.add_argument("--mode", default="vector", choices=["bm25", "vector", "hybrid"])
    se.add_argument("--root", default="library")
    sv = sub.add_parser("serve", help="(M2) the gallery over local HTTP, for Studio")
    sv.add_argument("--root", default="library")
    sv.add_argument("--port", type=int, default=8772)
    sv.add_argument("--sadhu", default=None, help="a sadhu checkout: turns on the director")
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
    elif args.cmd == "library":
        _library(args)
    elif args.cmd == "search":
        from vector_director.m2_retrieval.serve import Gallery

        for h in Gallery(args.root).search(args.query, args.k, args.kind, None, args.mode):
            print(f"{h['score']:.3f}  {h['id']:40} {h['status']:9} {h['height_cm']:g} cm")
    elif args.cmd == "serve":
        from vector_director.m2_retrieval.serve import serve

        serve(args.root, args.port, args.sadhu)
    elif args.cmd == "set":
        _set(args)


def _library(args: argparse.Namespace) -> None:
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from vector_director.m2_retrieval import library as lib
    from vector_director.m2_retrieval.embedders import ClipEmbedder
    from vector_director.m2_retrieval.retrievers import (
        BM25Retriever,
        HybridRetriever,
        VectorRetriever,
    )

    reg = lib.Registry(args.root)
    if args.action == "openclipart":
        from vector_director.m2_retrieval.sources import download_openclipart

        print(download_openclipart(Path("data/raw/openclipart")))
    if args.action in ("seed", "openmoji", "openclipart", "thumbs"):
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            if args.action == "seed":
                print(lib.seed_sadhu(reg, Path(args.sadhu), page))
            elif args.action == "openclipart":
                from vector_director.m2_retrieval.sources import seed_openclipart

                print(seed_openclipart(reg, Path("data/raw/openclipart"), page))
            elif args.action == "openmoji":
                root = Path(args.openmoji)
                meta = json.loads((root / "openmoji.json").read_text())
                heights = json.loads(Path(args.heights).read_text()) if args.heights else None
                print(lib.seed_openmoji(reg, root / "color", meta, page, heights))
            else:
                print("thumbs", lib.make_thumbs(reg, page))
            browser.close()
    elif args.action == "label":
        from vector_director.m1_harness.llm import make_llm
        from vector_director.m2_retrieval.sources import label_openclipart

        print(label_openclipart(reg, make_llm("gemini", "gemini-3.8-flash")))
    elif args.action == "embed":
        print("embedded", VectorRetriever(reg, ClipEmbedder()).build())
    elif args.action == "eval":
        from vector_director.m2_retrieval.metrics import mrr, recall_at_k

        labels = [json.loads(x) for x in Path(args.labels).read_text().splitlines() if x.strip()]
        bm25, vector = BM25Retriever(reg), VectorRetriever(reg, ClipEmbedder())
        for name, r in {"bm25": bm25, "vector": vector, "hybrid": HybridRetriever([bm25, vector], [1, 3])}.items():
            rec, rr = 0.0, 0.0
            for row in labels:
                ranked = [h.id for h in r.search(row["query"], k=50, kind="prop")]
                good = set(row["relevant"])
                rec += recall_at_k(ranked, good, 10)
                rr += mrr(ranked, good)
            print(f"{name:7} recall@10 {rec / len(labels):.3f}   mrr {rr / len(labels):.3f}   ({len(labels)} queries)")


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
