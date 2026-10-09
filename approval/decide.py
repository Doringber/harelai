"""The assignment's approval rules, and the final JSON. Plain code: the model never decides."""

# Rule name -> (field, documents allowed to prove it). All rules must hold to APPROVE.
RULES = {
    "Suspicious nodule requiring investigation": [("suspicious_nodule", ["ct", "clinical"])],
    "Tissue sampling recommended": [("tissue_sampling", ["ct", "clinical"])],
    "Requested procedure fits the findings and the patient": [("procedure_supported", ["request", "clinical"])],
    "Preliminary tests show no clear barrier": [("labs_acceptable", ["labs"]), ("pulmonary_acceptable", ["pft"])],
}

# Where to look first for each summary value.
PREFER = ["ct", "pft", "labs", "clinical", "request"]


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
        lobe = (value(facts, "location") or "").split(",")[0]
        # ICD-10 J44 = COPD; the model may return the code alone or with its description.
        copd = any(d.startswith("J44") or "obstructive pulmonary" in d.casefold() for d in value(facts, "diagnoses") or [])
        condition = "COPD" if copd else "pulmonary condition"
        fev1 = value(facts, "fev1_percent")
        reason = (f"The clinical findings support tissue diagnosis of a suspicious {lobe} pulmonary nodule "
                  f"(Lung-RADS {value(facts, 'lung_rads')}), and the requested procedure is appropriate based on the "
                  f"lesion location and the patient's {condition}" + (f" (FEV1 {fev1}% predicted)." if fev1 else "."))
        return "APPROVE", reason, rules
    problems = [name for name, ok in rules.items() if not ok] + blocking
    if contraindicated:
        problems.append("a document states a contraindication")
    return "MANUAL_REVIEW", "Manual review required: " + "; ".join(problems), rules


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
            "finding": f"Suspicious {location.split(',')[0]} pulmonary nodule" if suspicious and location else None,
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
        "rules": rules,
        "issues": issues,
        "evidence": {role: {f: fact["quote"] for f, fact in fields.items()} for role, fields in facts.items()},
        "model": model,
    }
