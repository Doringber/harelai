"""Usage: python -m approval [case.json] [--model gemma4] [--output result.json]"""
import argparse
import json
import time
from pathlib import Path

from approval.check import check, issue
from approval.decide import build_result
from approval.extract import extract
from approval.read import read_pdf


def run_case(case_file: Path, model: str, extract_fn=extract) -> dict:
    """Read every document, extract facts, check them, decide. One bad document never stops the others."""
    documents = json.loads(case_file.read_text())["documents"]
    texts, answers, issues = {}, {}, []
    for doc in documents:
        role, path = doc["role"], case_file.parent / doc["path"]
        start = time.monotonic()
        try:
            texts[role] = read_pdf(path)
            if len(texts[role].strip()) < 20:
                raise ValueError("no text found (scanned PDF? OCR is not supported)")
            answers[role] = extract_fn(role, texts[role], model)
            print(f"  {role:<9} ok      {time.monotonic() - start:5.1f}s")
        except Exception as exc:  # report and continue with the other documents
            issues.append(issue("blocking", f"{role}: could not process {path.name}: {exc}"))
            print(f"  {role:<9} FAILED  {exc}")
    facts, check_issues = check(texts, answers)
    return build_result(facts, issues + check_issues, model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prior authorization review with a local Ollama model")
    parser.add_argument("case", nargs="?", default="case.json", type=Path, help="case file listing the documents")
    parser.add_argument("--model", default="gemma4", help="local Ollama model (default: gemma4)")
    parser.add_argument("--output", default="result.json", type=Path)
    args = parser.parse_args()

    print(f"Reviewing {args.case} with {args.model}")
    result = run_case(args.case, args.model)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n{result['recommendation']['status']}: {result['recommendation']['reason']}")
    for i in result["issues"]:
        print(f"  [{i['severity']}] {i['detail']}")
    print(f"Full output: {args.output}")


if __name__ == "__main__":
    main()
