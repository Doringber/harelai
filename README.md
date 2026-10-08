# Version 0.2: Gradio and Groq

Start the interface with `python -m pip install -r requirements.txt` then `python app.py`.
The new UI includes fictional demo cases, source inspection, all four decision conditions, full JSON, execution traces and protected live uploads. Groq with `openai/gpt-oss-120b` is the default live provider; Claude remains available. See [deployment instructions](docs/DEPLOYMENT.md).

`space-ready/` is an allowlisted deployment folder without the original medical PDFs. The full project still includes those inputs under `examples/` for local assignment testing. No credentials are included. A hosted Space has not yet been published. A real Groq run on the fictional demo returned APPROVE and is included under `demo/groq-live.json`; the first manual-review run is also preserved. The original clinical files have not been sent to Groq.

The following sections describe the original core implementation; where they mention the default Claude provider, v0.2 now defaults to Groq.

# Medical prior authorization assignment

A modular Python prototype that processes the five supplied medical documents, extracts attributed facts, validates evidence and identity, and applies the assignment's four deterministic recommendation conditions. It returns APPROVE or MANUAL_REVIEW, a complete JSON record and an offline HTML evidence viewer.

**Delivery status:** the included result is an actual run of the local English-layout baseline on the supplied PDFs. It is clearly labeled `local-layout-baseline:v1`; it is not an LLM result. The Claude adapter is implemented and tested with simulated API responses, but a live Claude run has not been performed. Complete that run before submitting this as a finished AI assignment.

## Quick start

Python 3.11+ on macOS/Linux. From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m approval.cli examples/case.json --extractor local
python -m unittest discover -s tests -v
```

Open `output/report.html` in your browser. The full output is `output/result.json`. The five original input PDFs are included under `examples/input/`. The task-instructions Word file is deliberately excluded from the case and the model prompt. Input selection is explicit in the manifest; no folder-wide ingestion.

## Live Claude run

Set credentials only in your local shell. A ChatGPT or Claude chat subscription is not substituted for an API key. Choose an exact model ID available in your Anthropic account.

```bash
export ANTHROPIC_API_KEY='your-key'
export ANTHROPIC_MODEL='your-exact-model-id'
python -m approval.cli examples/case.json --extractor claude --output output/claude
```

`groq` is the CLI default in v0.2; select `--extractor claude` for Claude. Missing credentials fail visibly; there is no silent fallback to the local baseline. Five documents are processed separately. The adapter sends extracted text to `https://api.anthropic.com/v1/messages`, requests one structured tool result, and validates it locally with Pydantic. It cannot browse, execute commands or submit an authorization. API reference: https://platform.claude.com/docs/en/api/messages/create

The JSON and HTML contain the input clinical information and source excerpts. Keep them and the local SQLite database with the same access restrictions as the input files. API credentials are not stored in the database or outputs.

## OCR and formats

PDF, DOCX and UTF-8/UTF-16 text use separate readers behind one protocol. PDF page text is inspected for empty/sparse extraction, replacement/control characters, and large images with little extracted text. With `--ocr`, only suspect pages are rasterized and passed to Tesseract. Originals are never modified.

```bash
# macOS; install required languages separately if needed
brew install tesseract
# Ubuntu/Debian alternative: sudo apt-get install tesseract-ocr
python -m approval.cli examples/case.json --extractor local --ocr
# Additional language packs must exist locally:
# --ocr --ocr-languages eng+heb+ara
```

Each page records native/OCR provenance and quality warnings. DOCX/text locations are logical segments, not invented physical pages. DOCX tables are retained as rows; embedded image OCR and complex PDF table reconstruction are not implemented.

## Design

- `core/`: frozen Pydantic contracts, Unicode quality functions, evidence/case validation, and a pure decision function. No network, database, clock or filesystem operations.
- `readers/`: format-specific readers plus an isolated parser worker with a 90-second document deadline. OCR subprocesses have a 30-second page timeout.
- `extractors/`: swappable `Extractor` protocol, a narrowly scoped local baseline and Claude structured extraction. The prompt extracts facts; it does not decide approval.
- `application.py`: orchestration of explicit effects, checkpoints, validation and final output.
- `infrastructure/`: SQLite persistence and bounded transient retry policy.
- `presentation/`: escaped offline HTML showing criteria, warnings and expandable source quotations.
- `tests/`: decision, evidence, failure, cache, reader and provider-boundary regressions.

## Recommendation logic

All four conditions must be supported: a suspicious nodule, an explicit tissue-sampling recommendation, a rationale linking the requested procedure to the findings/condition, and documented laboratory plus pulmonary suitability. These qualitative assertions are extracted from source interpretations; no invented FEV1, SUV or coagulation cutoff is used. A documented contraindication, insufficient evidence, missing required document or material conflict leads to MANUAL_REVIEW. No DENY policy is invented.

Exact quote presence is checked against the supplied page. Extracted numeric values must appear in their quote. This verifies attribution, not full medical entailment; wrong-column readings and misleading quotes remain possible and need broader evaluation.

Every source document must carry name and date of birth. Critical identity and selected clinical conflicts block approval. Different reported ages are warnings when identity is consistent. PET findings from the request/clinical notes retain those citations and do not become a fabricated standalone PET report.

The summary uses the first observation for display; every conflicting observation is retained, and material conflicts block approval. A production version needs a richer temporal/lesion-aware reconciliation policy.

## Reliability and resume

Manifest validation precedes I/O. Files are limited to 20 MB, PDFs to 100 pages, case manifests to 20 documents, and Claude text context to 100,000 characters per document. Corrupt/unsupported files create blocking issues while other documents can finish. Missing/partial evidence is never treated as a complete case.

Transient provider connection failures and selected 408/429/5xx responses get at most three attempts with bounded exponential delay and jitter. Auth/client errors are not retried. One additional schema-repair request is allowed; with transient retries this can mean up to six HTTP attempts per document. Each HTTP operation has a 45-second socket timeout; an aggregate hard deadline is not implemented. Contradictions and invalid source quotations are routed to review, not endlessly retried.

Successful extraction checkpoints use content, document identity/role, reader output, extraction identity/model/prompt version, application version and OCR configuration. Resuming reuses successful extractions, reparses source documents, reruns evidence validation, and creates a new audited run. `--fresh` bypasses extraction checkpoints. SQLite uses WAL and transactional writes. This is a sequential local application: concurrent callers can duplicate provider work; distributed locks and exactly-once execution are not claimed.

Run execution status (`completed`, `partial`, `failed`) is independent from recommendation (`APPROVE`, `MANUAL_REVIEW`). A completed analysis can validly require manual review. CLI exit code 2 indicates input/config or operational failure, not a medical denial. The installed command and `python -m approval.cli` use the same CLI.

## Included evidence and remaining work

`examples/local-run/result.json` and `report.html` are generated from the provided documents. Expected values include 18 x 15 mm, Lung-RADS 4B, SUVmax 4.2, pre-BD FEV1 62%, DLCO 58%, normal documented coagulation, and APPROVE under the assignment policy. Age inconsistency and secondary PET provenance remain visible.

See `docs/VALIDATION.md` for what was actually tested and `docs/NEXT_STEPS.md` for scoped follow-up. This is assignment-specific recommendation support, not a validated clinical system or insurer coverage determination.
