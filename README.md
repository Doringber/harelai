# Medical prior-authorization review

A local AI workflow that reads a prior-authorization packet for robotic-assisted lung biopsy and returns **`APPROVE`** or **`MANUAL_REVIEW`** with a Hebrew explanation. PDFs and model requests stay on the local machine through Ollama; no hosted model API key is used.

## Codex plugin marketplace (optional)

To register the Anidoodle marketplace with Codex, run:

~~~bash
codex plugin marketplace add alexgreensh/anidoodle
~~~

This adds the marketplace source to Codex. It is separate from this app's runtime: the review application still runs with Python and local Ollama. See the [official Codex plugin documentation](https://developers.openai.com/plugins/build/plugins) for marketplace management.

## Architecture

~~~mermaid
flowchart LR
    A[Five medical PDFs] --> B[approval/read.py<br/>PyMuPDF text extraction]
    B --> C[approval/extract.py<br/>one-field Gemma extraction via Ollama]
    C --> D[approval/check.py<br/>quotes, dates, patient identity]
    D --> E[approval/decide.py<br/>deterministic approval rules]
    E --> F[result.json<br/>decision and evidence]
~~~

The model extracts a value and a supporting quote for one field at a time. Python checks that the quote appears in its source document, normalizes dates, compares patient identity, and applies the assignment's four rules. The model does not choose the authorization status.

The generated recommendation explanation, rule descriptions, issue descriptions, and console messages are in Hebrew. JSON field names and status codes remain stable in English (`APPROVE` and `MANUAL_REVIEW`); identifiers, codes, extracted values, and verbatim evidence quotes retain their source form.

## Requirements

- Python 3.11 or newer
- [Ollama](https://ollama.com) running locally
- Gemma 4 (or another locally installed Ollama model)

Install the model and project:

~~~bash
ollama pull gemma4
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
~~~

## Run the supplied case

From the repository root:

~~~bash
python -m approval case.json --model gemma4 --output result.json
~~~

The command reads the five PDFs listed in `case.json`, prints Hebrew progress and the recommendation, and writes the complete JSON result to `result.json`.

To use another local model or case file:

~~~bash
python -m approval path/to/case.json --model MODEL_NAME --output path/to/result.json
~~~

Each case JSON lists documents with a role (`request`, `clinical`, `ct`, `labs`, or `pft`) and a path relative to that JSON file.

## Run the alternate fictional case

The repository includes a synthetic second case to demonstrate a request that is not supported by the records. Rebuild its text PDFs if needed, then run it:

~~~bash
python ai/alternate_case/build_pdfs.py
python -m approval ai/alternate_case/case.json \
  --model gemma4:latest \
  --output ai/alternate_case/result.json
~~~

The current run returns `MANUAL_REVIEW`: the records describe a stable Lung-RADS 2 nodule and recommend imaging surveillance rather than tissue sampling. The full output is in `ai/alternate_case/result.json`.

## Decision rules

The app returns `APPROVE` only when all four rules are supported by the specified documents and no blocking issue is present:

| Rule | Evidence source |
|---|---|
| Suspicious nodule requiring investigation | CT report or clinical notes |
| Tissue sampling recommended | CT report or clinical notes |
| Requested procedure fits the findings and patient | Request form or clinical notes |
| Preliminary tests show no clear barrier | Laboratory report and PFT report |

Otherwise the app returns `MANUAL_REVIEW`. There is no automatic rejection path.

## Output

The complete output for the supplied case is in [`result.json`](result.json). It includes patient and request fields, clinical summary, Hebrew recommendation, rule outcomes, issues, exact source quotes, and the model name.

## Tests

The project has unit tests that use stubbed model answers and do not require Ollama:

~~~bash
pytest tests -q
~~~

## Known limits

- Text PDFs are supported; scanned PDFs require OCR, which is not included.
- Quote checking confirms that text occurs in a document; it does not prove that the quote semantically supports the extracted value.
- Patient name and date of birth are required for each processed document. MRN mismatches are checked when MRNs are present, but a missing MRN is not currently a blocking issue.
- Extraction is one model call per field, so a review can take about one minute or more depending on hardware and model.
- This is an assignment demonstration to support human review, not a validated clinical or insurance decision system.
