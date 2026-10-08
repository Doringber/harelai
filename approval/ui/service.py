"""UI application service. No Gradio dependency; all decisions stay in core/."""
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from approval.application import run
from approval.core.models import Result
from approval.extractors.claude import ClaudeExtractor
from approval.extractors.groq import GroqExtractor
from approval.extractors.local import LocalExtractor
from approval.infrastructure.store import Store

ROOT = Path(__file__).resolve().parents[2]
ROLES = ["request", "clinical", "ct", "labs", "pft"]
SCENARIOS = {"Complete case": "complete.json", "Missing laboratory report": "missing-labs.json"}
if (ROOT / "demo/groq-live.json").exists():
    SCENARIOS["Groq recorded run"] = "groq-live.json"

class LiveBudget:
    """Single-process spending guard. A restart resets it (documented)."""
    def __init__(self, limit):
        self.limit, self.used, self.lock = limit, 0, threading.Lock()
    def reserve(self):
        with self.lock:
            if self.used >= self.limit: raise ValueError("Live-run limit reached. The owner must review usage before restarting.")
            self.used += 1

BUDGET = LiveBudget(int(os.getenv("MAX_LIVE_RUNS", "3")))

def live_ready():
    provider = os.getenv("LLM_PROVIDER", "groq")
    configured = bool(os.getenv("GROQ_API_KEY")) if provider == "groq" else bool(os.getenv("ANTHROPIC_API_KEY") and os.getenv("ANTHROPIC_MODEL")) if provider == "claude" else False
    return configured and bool(os.getenv("APP_USERNAME") and os.getenv("APP_PASSWORD")) and os.getenv("ENABLE_LIVE") == "1"

def saved_case(scenario):
    if scenario not in SCENARIOS: raise ValueError("Unknown scenario")
    return Result.model_validate_json((ROOT / "demo" / SCENARIOS[scenario]).read_text())

def execute_case(scenario, live=False, uploads=None, ocr=False):
    if scenario not in SCENARIOS: raise ValueError("Unknown scenario")
    if live and not live_ready():
        raise ValueError("Live AI is disabled. The owner must configure model credentials and app authentication.")
    if uploads and any(uploads) and not live:
        raise ValueError("Uploaded documents require live AI; local extraction supports only the demonstration layout.")
    with tempfile.TemporaryDirectory(prefix="approval-run-") as temp:
        work = Path(temp)
        if uploads and any(uploads):
            entries = []
            for role, source in zip(ROLES, uploads, strict=True):
                if not source: continue  # Core marks missing roles as MANUAL_REVIEW.
                source = Path(source)
                if source.suffix.lower() not in (".pdf", ".docx", ".txt") or source.stat().st_size > 20_000_000:
                    raise ValueError("Each input must be PDF, DOCX or TXT and at most 20 MB.")
                target = work / (role + source.suffix.lower())
                shutil.copyfile(source, target)
                entries.append({"id": role, "role": role, "path": str(target)})
        else:
            entries = json.loads((ROOT / "demo/case.json").read_text())["documents"]
            entries = [dict(e, path=str(ROOT / "demo" / e["path"])) for e in entries if scenario != "Missing laboratory report" or e["role"] != "labs"]
        manifest = work / "case.json"
        manifest.write_text(json.dumps({"documents": entries}))
        if live: BUDGET.reserve()
        extractor = LocalExtractor()
        if live:
            extractor = GroqExtractor(os.getenv("GROQ_API_KEY"),os.getenv("GROQ_MODEL","openai/gpt-oss-120b")) if os.getenv("LLM_PROVIDER","groq") == "groq" else ClaudeExtractor(os.getenv("ANTHROPIC_API_KEY"), os.getenv("ANTHROPIC_MODEL"))
        store = Store(work / "run.sqlite")
        try: return run(manifest, extractor, store, ocr=ocr)
        finally: store.close()

def evidence_rows(result, query=""):
    query = query.casefold().strip()
    rows = []
    for o in result.observations:
        row = [o.field, str(o.value), o.evidence.document_id, o.evidence.page, o.evidence.quote]
        if not query or query in " ".join(map(str, row)).casefold(): rows.append(row)
    return rows
