"""Thin orchestration: I/O here, validation and decisions in core/."""
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from approval.core.models import Document, Page, Issue, Result
from approval.core.validation import validate_evidence, validate_case
from approval.core.decision import decide

VERSION = "app-v3"

def run(manifest, extractor, store, ocr=False, languages="eng", fresh=False):
    manifest = Path(manifest)
    entries = json.loads(manifest.read_text(encoding="utf-8"))["documents"]
    if not isinstance(entries, list) or not entries or len(entries) > 20:
        raise ValueError("Manifest must contain 1..20 explicit document entries")
    valid_roles = {"request", "clinical", "ct", "labs", "pft"}
    # Validate the complete manifest before any document or provider operation.
    if any(not isinstance(e, dict) or set(e) != {"id", "role", "path"} or
           not all(isinstance(e[k], str) and e[k] for k in e) or e["role"] not in valid_roles for e in entries):
        raise ValueError("Invalid manifest entry")
    if len({e["id"] for e in entries}) != len(entries): raise ValueError("Duplicate document ID")
    docs, observations, issues, trace = [], [], [], []
    seen, ids = set(), set()
    for entry in entries:
        start = time.monotonic()
        doc_id = entry["id"]
        if doc_id in ids: raise ValueError("Duplicate document ID")
        ids.add(doc_id)
        path = manifest.parent / entry["path"]
        try:
            if path.suffix.lower() not in (".pdf", ".docx", ".txt"): raise ValueError("unsupported_format")
            if path.stat().st_size > 20_000_000: raise ValueError("file_size_limit")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen:
                issues.append(Issue(code="duplicate_document", severity="warning", detail=doc_id))
                continue
            seen.add(digest)
            proc = subprocess.run([sys.executable, "-m", "approval.readers.worker"],
                input=json.dumps({"path": str(path.resolve()), "ocr": ocr, "languages": languages}),
                capture_output=True, text=True, timeout=90, check=True)
            pages = [Page.model_validate(x) for x in json.loads(proc.stdout)]
            doc = Document(id=doc_id, filename=path.name, role=entry["role"], sha256=digest, pages=pages)
            docs.append(doc)
            trace.append({"stage": "read", "document_id": doc_id, "status": "completed", "seconds": round(time.monotonic()-start, 3)})
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            issues.append(Issue(code="read_failed", severity="blocking", detail=f"{doc_id}: {type(exc).__name__}"))
            trace.append({"stage": "read", "document_id": doc_id, "status": "failed"})
            continue
        if not all(p.usable for p in doc.pages):
            # Partial text still kept as evidence, but cannot justify approval.
            issues.append(Issue(code="partial_document", severity="blocking", detail=doc_id))
        fingerprint = json.dumps([VERSION, extractor.identity, doc.model_dump(), ocr, languages], sort_keys=True)
        key = hashlib.sha256(fingerprint.encode()).hexdigest()
        start = time.monotonic()
        try:
            cached = None if fresh else store.get(key)
            extraction = cached if cached is not None else extractor.extract(doc)
            accepted, evidence_issues = validate_evidence(extraction.observations, [doc])
            if evidence_issues and cached is None:
                # Model output varies between calls; ask once more before blocking the document.
                extraction = extractor.extract(doc)
                accepted, evidence_issues = validate_evidence(extraction.observations, [doc])
            observations.extend(accepted)
            issues.extend(evidence_issues)
            if not cached and not evidence_issues: store.put(key, extraction)
            trace.append({"stage": "extract", "document_id": doc_id, "status": "completed" if not evidence_issues else "invalid_evidence",
                "cached": cached is not None, "seconds": round(time.monotonic()-start, 3),
                "usage": {} if cached is not None else getattr(extractor, "last_usage", {})})
        except Exception as exc:
            issues.append(Issue(code="extraction_failed", severity="blocking", detail=f"{doc_id}: {type(exc).__name__} {exc}".strip()))
            trace.append({"stage": "extract", "document_id": doc_id, "status": "failed", "error_type": type(exc).__name__})
    issues.extend(validate_case(docs, observations))
    recommendation = decide(observations, docs, issues)
    role_of = {d.id: d.role for d in docs}
    def value(field):
        # Prefer the radiology report for lesion details (it has the full size); otherwise first observation.
        ranked = sorted(observations, key=lambda o: role_of.get(o.evidence.document_id) != "ct")
        return next((o.value for o in ranked if o.field == field), None)
    failures = any(i.code in ("read_failed", "extraction_failed", "partial_document", "invalid_evidence") for i in issues)
    result = Result(run_id=str(uuid.uuid4()), run_status="failed" if not observations else "partial" if failures else "completed",
        extraction_mode=extractor.identity, case_id=value("case_id"),
        patient={k: value(k) for k in ("name", "date_of_birth", "mrn")},
        request={k: value(k) for k in ("provider", "procedure", "cpt_codes", "diagnoses", "requested_date", "facility")},
        clinical_summary={k: value(k) for k in ("finding", "location", "nodule_size", "characteristics", "lung_rads", "suv_max",
            "risk_brock_percent", "risk_mayo_percent", "fev1_percent", "dlco_percent", "coagulation_status", "laboratory_status", "rationale")},
        recommendation=recommendation, issues=issues, observations=observations, documents=docs, trace=trace)
    store.save_run(result)
    return result
