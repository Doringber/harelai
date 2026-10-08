import re
from collections import defaultdict
from datetime import date
from .models import Document, Observation, Issue, NUMBER_FIELDS
from .quality import normalize

REQUIRED_ROLES = {"request", "clinical", "ct", "labs", "pft"}
# Missing these prevents a complete, attributable recommendation.
REQUIRED_FIELDS = {"case_id", "name", "date_of_birth", "mrn", "provider", "procedure",
    "cpt_codes", "diagnoses", "requested_date", "facility", "finding", "nodule_size",
    "location", "characteristics", "lung_rads", "suv_max", "risk_brock_percent",
    "fev1_percent", "dlco_percent", "coagulation_status", "laboratory_status", "rationale"}
CRITICAL = {"case_id", "name", "date_of_birth", "mrn", "procedure", "requested_date",
            "lung_rads", "suv_max", "fev1_percent", "dlco_percent", "coagulation_status"}

REQUEST_ONLY = {"procedure", "requested_date"}

def canonical(field, value):
    if isinstance(value, str):
        s = normalize(value).casefold()
        if field == "lung_rads":
            s = re.sub(r"^(?:lung[- ]rads\s*)?(?:category\s*)?", "", s).strip(": ")
            return s
        if field == "name": return " ".join(sorted(s.replace(",", " ").replace(".", " ").split()))
        return s
    return tuple(sorted(value)) if isinstance(value, list) else value

def validate_evidence(observations: list[Observation], documents: list[Document]):
    lookup = {d.id: d for d in documents}
    accepted, issues = [], []
    for o in observations:
        d = lookup.get(o.evidence.document_id)
        p = next((p for p in d.pages if p.number == o.evidence.page), None) if d else None
        if p is None or not p.usable or normalize(o.evidence.quote) not in normalize(p.text):
            issues.append(Issue(code="invalid_evidence", severity="blocking", detail=f"Unverifiable evidence for {o.field}"))
        elif o.field in NUMBER_FIELDS and not any(float(n) == o.value for n in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", o.evidence.quote)):
            issues.append(Issue(code="invalid_evidence", severity="blocking", detail=f"Numeric value absent from quote for {o.field}"))
        else:
            accepted.append(o)
    return accepted, issues

def validate_case(documents: list[Document], observations: list[Observation]):
    issues = []
    missing = REQUIRED_ROLES - {d.role for d in documents}
    if missing:
        issues.append(Issue(code="missing_documents", severity="blocking", detail=", ".join(sorted(missing))))
    for d in documents:
        for p in d.pages:
            if not p.usable:
                issues.append(Issue(code="unreadable_page", severity="blocking", detail=f"{d.id} segment {p.number}"))
    grouped = defaultdict(list)
    for o in observations: grouped[o.field].append(o)
    missing_fields = REQUIRED_FIELDS - grouped.keys()
    if missing_fields:
        issues.append(Issue(code="missing_fields", severity="blocking", detail=", ".join(sorted(missing_fields))))
    roles = {d.id: d.role for d in documents}
    for field in CRITICAL:
        # The requested procedure/date are defined by the request form only; other documents mention other exams and dates.
        scoped = [o for o in grouped[field] if field not in REQUEST_ONLY or roles.get(o.evidence.document_id) == "request"]
        values = {canonical(field, o.value) for o in scoped}
        if len(values) > 1:
            issues.append(Issue(code="material_conflict", severity="blocking", detail=f"Conflicting {field}; all observations retained"))
    # Every document must be attributable, not just the aggregate case.
    for d in documents:
        fields = {o.field for o in observations if o.evidence.document_id == d.id}
        if not {"name", "date_of_birth"} <= fields:
            issues.append(Issue(code="unlinked_document", severity="blocking", detail=d.id))
    if len({o.value for o in grouped["reported_age"]}) > 1:
        issues.append(Issue(code="age_discrepancy", severity="warning", detail="Reported ages differ; consistent name/DOB/MRN take precedence"))
    for field in ("date_of_birth", "requested_date"):
        for o in grouped[field]:
            try: date.fromisoformat(str(o.value))
            except ValueError:
                issues.append(Issue(code="invalid_date", severity="blocking", detail=field))
    if grouped["suv_max"]:
        issues.append(Issue(code="pet_secondary_source", severity="warning", detail="PET result is documented in request/clinical notes; no standalone PET report supplied"))
    return issues
