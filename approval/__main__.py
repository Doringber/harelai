"""Usage: python -m approval [case.json] [--model gemma4] [--output result.json]"""
import argparse
import json
import time
from pathlib import Path

from approval.check import check, issue, role_label_he
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
            print(f"  {role_label_he(role)}: הושלם ({time.monotonic() - start:.1f} שניות)")
        except Exception:  # report and continue with the other documents
            issues.append(issue(
                "blocking",
                f"לא ניתן לעבד את הקובץ {path.name} עבור {role_label_he(role)}.",
            ))
            print(f"  {role_label_he(role)}: העיבוד נכשל.")
    facts, check_issues = check(texts, answers)
    return build_result(facts, issues + check_issues, model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prior authorization review with a local Ollama model")
    parser.add_argument("case", nargs="?", default="case.json", type=Path, help="case file listing the documents")
    parser.add_argument("--model", default="gemma4", help="local Ollama model (default: gemma4)")
    parser.add_argument("--output", default="result.json", type=Path)
    args = parser.parse_args()

    print(f"בודק את {args.case} באמצעות המודל המקומי {args.model}")
    result = run_case(args.case, args.model)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    status_label = "אושר" if result["recommendation"]["status"] == "APPROVE" else "נדרשת בדיקה ידנית"
    print(f"\n{status_label} ({result['recommendation']['status']}): {result['recommendation']['reason']}")
    for i in result["issues"]:
        severity = "חסימה" if i["severity"] == "blocking" else "אזהרה"
        print(f"  [{severity}] {i['detail']}")
    print(f"התוצאה המלאה נשמרה בקובץ: {args.output}")


if __name__ == "__main__":
    main()
