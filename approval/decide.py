"""The assignment's approval rules, and the final JSON. Plain code: the model never decides."""

# Rule name -> (field, documents allowed to prove it). All rules must hold to APPROVE.
RULES = {
    "Suspicious nodule requiring investigation": [("suspicious_nodule", ["ct", "clinical"])],
    "Tissue sampling recommended": [("tissue_sampling", ["ct", "clinical"])],
    "Requested procedure fits the findings and the patient": [("procedure_supported", ["request", "clinical"])],
    "Preliminary tests show no clear barrier": [("labs_acceptable", ["labs"]), ("pulmonary_acceptable", ["pft"])],
}

RULE_LABELS_HE = {
    "Suspicious nodule requiring investigation": "נודול חשוד המצריך בירור",
    "Tissue sampling recommended": "הומלצה דגימת רקמה",
    "Requested procedure fits the findings and the patient": "הפרוצדורה המבוקשת מתאימה לממצאים ולמצב הרפואי",
    "Preliminary tests show no clear barrier": "הבדיקות המקדימות אינן מצביעות על מניעה ברורה",
}

RULE_PROBLEMS_HE = {
    "Suspicious nodule requiring investigation": "לא הוכח שקיים נודול חשוד המצריך בירור",
    "Tissue sampling recommended": "לא הוכחה המלצה לדגימת רקמה",
    "Requested procedure fits the findings and the patient": "לא הוכחה התאמת הפרוצדורה לממצאים ולמצב הרפואי",
    "Preliminary tests show no clear barrier": "לא הוכח שהבדיקות המקדימות אינן מצביעות על מניעה ברורה",
}

# Where to look first for each summary value.
PREFER = ["ct", "pft", "labs", "clinical", "request"]


def hebrew_location(location: str | None) -> str:
    normalized = (location or "").casefold()
    locations = (
        ("right upper lobe", "באונה הימנית העליונה"),
        ("left upper lobe", "באונה השמאלית העליונה"),
        ("right middle lobe", "באונה הימנית האמצעית"),
        ("right lower lobe", "באונה הימנית התחתונה"),
        ("left lower lobe", "באונה השמאלית התחתונה"),
    )
    return next((label for match, label in locations if match in normalized), "במיקום המתואר במסמכים")


def flag(facts: dict, field: str, roles: list[str]) -> bool:
    """True only if at least one allowed document says yes and none says no."""
    values = [facts[r][field]["value"] for r in roles if field in facts.get(r, {})]
    return bool(values) and all(values)


def value(facts: dict, field: str, prefer: list[str] = PREFER):
    for role in prefer:
        if field in facts.get(role, {}):
            v = facts[role][field]["value"]
            return int(v) if isinstance(v, float) and v.is_integer() else v
    return None


def display_name(name: str | None) -> str | None:
    """'JOHNSON, MARGARET A.' -> 'Margaret A. Johnson'."""
    if name and "," in name:
        last, first = name.split(",", 1)
        name = f"{first.strip()} {last.strip()}"
    return name.title() if name and name.isupper() else name


def decide(facts: dict, issues: list[dict]) -> tuple[str, str, dict]:
    """Return (status, reason, rule results)."""
    rules = {name: all(flag(facts, f, roles) for f, roles in needs) for name, needs in RULES.items()}
    contraindicated = any(f.get("contraindication", {}).get("value") is True for f in facts.values())
    blocking = [i["detail"] for i in issues if i["severity"] == "blocking"]
    if all(rules.values()) and not contraindicated and not blocking:
        # ICD-10 J44 = COPD; the model may return the code alone or with its description.
        copd = any(d.startswith("J44") or "obstructive pulmonary" in d.casefold() for d in value(facts, "diagnoses") or [])
        fev1 = value(facts, "fev1_percent")
        lung_rads = value(facts, "lung_rads") or "לא צוין"
        reason = (
            f"הממצאים הקליניים תומכים בדגימת רקמה מנודול חשוד {hebrew_location(value(facts, 'location'))} "
            f"(Lung-RADS {lung_rads}). הפרוצדורה המבוקשת מתאימה למיקום הנגע ולמצב הריאתי המתואר במסמכים"
        )
        if copd:
            reason += " על רקע COPD"
        if fev1:
            reason += f" (FEV1 של {fev1}% מהצפוי)."
        else:
            reason += "."
        return "APPROVE", reason, rules
    problems = [RULE_PROBLEMS_HE[name] for name, ok in rules.items() if not ok] + blocking
    if contraindicated:
        problems.append("באחד המסמכים תועדה מניעה לביצוע הפרוצדורה")
    return "MANUAL_REVIEW", "נדרשת בדיקה ידנית: " + "; ".join(problems), rules


def build_result(facts: dict, issues: list[dict], model: str) -> dict:
    status, reason, rules = decide(facts, issues)
    location = value(facts, "location")
    suspicious = flag(facts, "suspicious_nodule", ["ct", "clinical"])
    return {
        "case_id": value(facts, "case_id"),
        "patient": {
            "name": display_name(value(facts, "patient_name")),
            "date_of_birth": value(facts, "date_of_birth"),
            "mrn": value(facts, "mrn"),
        },
        "request": {
            "procedure": value(facts, "procedure"),
            "cpt_codes": value(facts, "cpt_codes"),
            "requested_date": value(facts, "requested_date"),
            "provider": value(facts, "provider"),
            "diagnoses": value(facts, "diagnoses"),
            "facility": value(facts, "facility"),
        },
        "clinical_summary": {
            "finding": f"נודול חשוד {hebrew_location(location)}" if suspicious and location else None,
            "nodule_size": value(facts, "nodule_size"),
            "lung_rads": value(facts, "lung_rads"),
            "suv_max": value(facts, "suv_max"),
            "fev1_percent": value(facts, "fev1_percent"),
            "dlco_percent": value(facts, "dlco_percent"),
            "coagulation_status": value(facts, "coagulation_status"),
            "location": location,
            "characteristics": value(facts, "characteristics"),
            "malignancy_risk": value(facts, "malignancy_risk"),
            "procedure_rationale": value(facts, "rationale", ["request", "clinical"]),  # the request states it in full
        },
        "recommendation": {"status": status, "reason": reason},
        "rules": {RULE_LABELS_HE[name]: met for name, met in rules.items()},
        "issues": issues,
        "evidence": {role: {f: fact["quote"] for f, fact in fields.items()} for role, fields in facts.items()},
        "model": model,
    }
