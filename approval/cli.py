import argparse
import os
from pathlib import Path
from approval.application import run
from approval.extractors.local import LocalExtractor
from approval.extractors.claude import ClaudeExtractor
from approval.extractors.groq import GroqExtractor
from approval.infrastructure.store import Store
from approval.presentation.report import render

def main():
    p = argparse.ArgumentParser(description="Prior authorization assignment prototype")
    p.add_argument("manifest", type=Path)
    p.add_argument("--extractor", choices=["local", "claude", "groq"], default="groq")
    p.add_argument("--output", type=Path, default=Path("output"))
    p.add_argument("--db", type=Path, default=Path("output/runs.sqlite"))
    p.add_argument("--ocr", action="store_true")
    p.add_argument("--ocr-languages", default="eng")
    p.add_argument("--fresh", action="store_true", help="Ignore successful extraction checkpoints")
    args = p.parse_args()
    try:
        extractor = (LocalExtractor() if args.extractor == "local" else GroqExtractor(os.getenv("GROQ_API_KEY"),os.getenv("GROQ_MODEL","openai/gpt-oss-120b")) if args.extractor == "groq" else ClaudeExtractor(os.getenv("ANTHROPIC_API_KEY"), os.getenv("ANTHROPIC_MODEL")))
        store = Store(args.db)
        try: result = run(args.manifest, extractor, store, args.ocr, args.ocr_languages, args.fresh)
        finally: store.close()
    except (ValueError, OSError, KeyError) as exc:
        p.exit(2, f"Cannot run: {type(exc).__name__}: check manifest, input paths, and provider environment.\n")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    (args.output / "report.html").write_text(render(result), encoding="utf-8")
    print(f"{result.run_status}: {result.recommendation.status}; mode={result.extraction_mode}")
    print(f"Results: {args.output / 'result.json'} and {args.output / 'report.html'}")
    return 0 if result.run_status == "completed" else 2

if __name__ == "__main__":
    raise SystemExit(main())
