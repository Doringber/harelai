"""Check the model's answers against the documents. Bad answers are dropped and reported."""
import re
from datetime import datetime

ROLES = ["request", "clinical", "ct", "labs", "pft"]

ROLE_LABELS_HE = {
    "request": "בקשת האישור",
    "clinical": "הסיכום הרפואי",
    "ct": "דו״ח ה־CT",
    "labs": "בדיקות המעבדה",
    "pft": "בדיקות תפקודי הריאה",
}

FIELD_LABELS_HE = {
    "patient_name": "שם המטופל/ת",
    "date_of_birth": "תאריך הלידה",
    "mrn": "מספר הרשומה הרפואית",
    "case_id": "מספר הבקשה",
    "provider": "הרופא/ה המבקש/ת",
    "procedure": "הפרוצדורה המבוקשת",
    "cpt_codes": "קודי CPT",
    "diagnoses": "האבחנות",
    "requested_date": "תאריך השירות המבוקש",
    "facility": "המוסד הרפואי",
    "suv_max": "ערך SUVmax",
    "location": "מיקום הנודול",
    "nodule_size": "גודל הנודול",
    "characteristics": "מאפייני הנודול",
    "lung_rads": "קטגוריית Lung-RADS",
    "malignancy_risk": "הערכת הסיכון לממאירות",
    "coagulation_status": "מצב הקרישה",
    "fev1_percent": "FEV1",
    "dlco_percent": "DLCO",
    "rationale": "נימוק לבחירת הפרוצדורה",
    "suspicious_nodule": "חשד לנודול",
    "tissue_sampling": "המלצה לדגימת רקמה",
    "procedure_supported": "התאמת הפרוצדורה",
    "labs_acceptable": "התאמת בדיקות המעבדה",
    "pulmonary_acceptable": "התאמת תפקודי הריאה",
    "contraindication": "התוויית נגד",
}


def role_label_he(role: str) -> str:
    return ROLE_LABELS_HE.get(role, "תפקיד לא מוכר")


def field_label_he(field: str) -> str:
    return FIELD_LABELS_HE.get(field, "שדה לא מזוהה")


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
    issues = [
        issue("blocking", f"חסר מסמך: {role_label_he(r)}")
        for r in ROLES if r not in answers
    ]
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
            role_label = role_label_he(role)
            field_label = field_label_he(field)
            issues.append(issue(
                "blocking" if risky else "warning",
                f"{role_label}: הציטוט עבור {field_label} לא נמצא במסמך ולכן הערך הושמט.",
            ))

    for field in ("date_of_birth", "requested_date"):
        for role in facts:
            if field in facts[role]:
                iso = to_iso(facts[role][field]["value"])
                if iso:
                    facts[role][field]["value"] = iso
                else:
                    issues.append(issue(
                        "blocking",
                        f"{role_label_he(role)}: {field_label_he(field)} אינו תאריך תקין.",
                    ))

    # Every document must be about the same patient.
    for field, same in (("patient_name", same_name), ("date_of_birth", str.__eq__), ("mrn", str.__eq__)):
        seen = {r: facts[r][field]["value"] for r in facts if field in facts[r]}
        values = list(seen.values())
        if any(not same(values[0], v) for v in values[1:]):
            issues.append(issue(
                "blocking",
                f"המסמכים אינם תואמים בפרט {field_label_he(field)}.",
            ))
    for role in facts:
        if "patient_name" not in facts[role] or "date_of_birth" not in facts[role]:
            issues.append(issue(
                "blocking",
                f"{role_label_he(role)}: לא ניתן לאמת שם ותאריך לידה.",
            ))
    return facts, issues
