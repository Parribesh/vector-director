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
    ev.add_argument("--generator", default="api-spec")
    ev.add_argument("--prompts", default="data/eval/prompts.txt")
    args = parser.parse_args(argv)

    if args.cmd == "milestones":
        for mod, title in MILESTONES.items():
            print(f"{mod:16} {title}")
    elif args.cmd == "schema":
        from vector_director.core import AnimationSpec

        print(json.dumps(AnimationSpec.model_json_schema(), indent=2))
    elif args.cmd == "eval":
        raise SystemExit("eval arrives with M1")


if __name__ == "__main__":
    main()
