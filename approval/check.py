"""Check the model's answers against the documents. Bad answers are dropped and reported."""
import re
from datetime import datetime

ROLES = ["request", "clinical", "ct", "labs", "pft"]


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def issue(severity: str, detail: str) -> dict:
    return {"severity": severity, "detail": detail}


def quote_ok(fact: dict, text: str) -> bool:
    """The quote must appear in the document; a number must appear in its quote."""
    if normalize(fact["quote"]) not in normalize(text):
        return False
    if isinstance(fact["value"], float):
        numbers = re.findall(r"\d+(?:\.\d+)?", fact["quote"])
        return any(float(n) == fact["value"] for n in numbers)
    return True


def to_iso(text: str) -> str | None:
    """'03/15/1952', 'March 15, 1952' and '1952-03-15' all become '1952-03-15'. The model's format is not trusted."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def same_name(a: str, b: str) -> bool:
    """'JOHNSON, MARGARET A.' and 'Margaret A Johnson' are the same name."""
    words = lambda s: sorted(re.sub(r"[.,]", " ", s).casefold().split())
    return words(a) == words(b)


def check(texts: dict[str, str], answers: dict[str, dict]) -> tuple[dict, list[dict]]:
    """Return (verified facts per role, issues). A 'blocking' issue prevents approval."""
    issues = [issue("blocking", f"missing document: {r}") for r in ROLES if r not in answers]
    facts = {}
    for role, fields in answers.items():
        facts[role] = {}
        for field, fact in fields.items():
            if fact is None:
                continue
            if quote_ok(fact, texts[role]):
                facts[role][field] = fact
                continue
            # Block only if the lost answer argued against approval (a "no", or a contraindication "yes");
            # losing an answer in favour of approval only makes approval harder.
            risky = fact["value"] is True if field == "contraindication" else fact["value"] is False
            issues.append(issue("blocking" if risky else "warning", f"{role}.{field}: quote not found in document, ignored"))

    for field in ("date_of_birth", "requested_date"):
        for role in facts:
            if field in facts[role]:
                iso = to_iso(facts[role][field]["value"])
                if iso:
                    facts[role][field]["value"] = iso
                else:
                    issues.append(issue("blocking", f"{role}.{field}: not a valid date"))

    # Every document must be about the same patient.
    for field, same in (("patient_name", same_name), ("date_of_birth", str.__eq__), ("mrn", str.__eq__)):
        seen = {r: facts[r][field]["value"] for r in facts if field in facts[r]}
        values = list(seen.values())
        if any(not same(values[0], v) for v in values[1:]):
            issues.append(issue("blocking", f"documents disagree on {field}: {seen}"))
    for role in facts:
        if "patient_name" not in facts[role] or "date_of_birth" not in facts[role]:
            issues.append(issue("blocking", f"{role}: cannot confirm patient name and date of birth"))
    return facts, issues
