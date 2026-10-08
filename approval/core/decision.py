from .models import Criterion, Recommendation

# These are the assignment's four qualitative conditions, not a medical coverage policy.
SPECS = [
    ("Suspicious nodule requiring investigation", [("suspicious_nodule", {"ct", "clinical"})]),
    ("Tissue sampling recommended", [("tissue_sampling", {"ct", "clinical"})]),
    ("Requested procedure supported by documented rationale", [("procedure_supported", {"clinical", "request"})]),
    ("Preliminary tests do not document a clear barrier", [("labs_acceptable", {"labs"}), ("pulmonary_acceptable", {"pft"})]),
]

def decide(observations, documents, issues):
    roles = {d.id: d.role for d in documents}
    criteria = []
    for label, requirements in SPECS:
        met, evidence = True, []
        for field, allowed_roles in requirements:
            candidates = [o for o in observations if o.field == field and roles.get(o.evidence.document_id) in allowed_roles]
            met = met and bool(candidates) and all(o.value is True for o in candidates)
            evidence.extend(o.evidence for o in candidates)
        criteria.append(Criterion(name=label, met=met, evidence=evidence))
    contraindications = [o for o in observations if o.field == "contraindication" and o.value is True]
    blocked = any(i.severity == "blocking" for i in issues) or bool(contraindications)
    approve = all(c.met for c in criteria) and not blocked
    if approve:
        reason = "The submitted documentation supports tissue sampling of a suspicious pulmonary nodule. The requested procedure is supported by the documented lesion location and pulmonary condition; preliminary tests document no clear barrier under the assignment rules."
    else:
        reasons = [i.code + ": " + i.detail for i in issues if i.severity == "blocking"]
        reasons += [c.name for c in criteria if not c.met]
        if contraindications: reasons.append("Documented potential contraindication requires review")
        reason = "Manual review required: " + "; ".join(reasons)
    return Recommendation(status="APPROVE" if approve else "MANUAL_REVIEW", reason=reason, criteria=criteria)
