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

- [Git](https://git-scm.com/downloads)
- [Python 3.11 or newer](https://www.python.org/downloads/)
- [Ollama](https://ollama.com/download), installed and running locally

## First run: clone the project and see the result

Follow these steps from a terminal. The supplied case uses the five PDFs listed in `case.json`.

### macOS or Linux

1. Clone the GitHub repository and enter its folder:

   ~~~bash
   git clone https://github.com/Doringber/harelai.git
   cd harelai
   ~~~

2. Download Gemma 4. This downloads the local model and may take a while. Make sure Ollama is installed and running first.

   ~~~bash
   ollama pull gemma4
   ~~~

3. Create a Python environment and install the project. Run these commands from inside the `harelai` folder:

   ~~~bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -e .
   ~~~

4. Review the supplied case. The program prints Hebrew progress and its recommendation, then saves the complete result as `result.json` in the project folder.

   ~~~bash
   python -m approval case.json --model gemma4 --output result.json
   ~~~

5. Print just the decision and its Hebrew explanation:

   ~~~bash
   python -c 'import json; r=json.load(open("result.json", encoding="utf-8"))["recommendation"]; print("Status:", r["status"]); print("Hebrew explanation:", r["reason"])'
   ~~~

   To inspect every field, including the evidence quotes, run `python -m json.tool result.json` or open `result.json` in a text editor. The supplied case currently returns `APPROVE`; model and hardware differences can affect extraction and the result.

### Windows PowerShell

Install Git, Python 3.11 or newer, and [Ollama for Windows](https://ollama.com/download), then open PowerShell. Clone the project and download the model:

~~~powershell
git clone https://github.com/Doringber/harelai.git
cd harelai
ollama pull gemma4
~~~

Create the Python environment and install the project with its Python executable:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
~~~

Run the supplied case and print the decision with its Hebrew explanation:

~~~powershell
.\.venv\Scripts\python.exe -m approval case.json --model gemma4 --output result.json
.\.venv\Scripts\python.exe -c 'import json; r=json.load(open("result.json", encoding="utf-8"))["recommendation"]; print("Status:", r["status"]); print("Hebrew explanation:", r["reason"])'
~~~

Keep Ollama running while the review command runs. When you open a new terminal later, go back to the project folder. On macOS or Linux, activate the environment again with `source .venv/bin/activate`; on Windows, run the app using the Python executable shown above.

To use another local model or case file:

~~~bash
python -m approval path/to/case.json --model MODEL_NAME --output path/to/result.json
~~~

## Use a different set of PDFs

Put the new PDFs together with a case JSON file. In the JSON, point each role at the PDF that contains that kind of information. Paths are relative to the case JSON file. For example, if the files are in `cases/new-case/`:

~~~json
{
  "documents": [
    {"role": "request", "path": "request.pdf"},
    {"role": "clinical", "path": "clinical-notes.pdf"},
    {"role": "ct", "path": "ct-report.pdf"},
    {"role": "labs", "path": "lab-report.pdf"},
    {"role": "pft", "path": "pulmonary-function.pdf"}
  ]
}
~~~

Save that as `cases/new-case/case.json`, alongside those five PDFs, then run:

~~~bash
python -m approval cases/new-case/case.json \
  --model gemma4 \
  --output cases/new-case/result.json
~~~

The role tells the extractor which fields to look for; the filename itself does not determine the check:

| Role | Fields used in review |
|---|---|
| `request` | Requested procedure, codes, diagnoses, date, provider, facility, and procedure rationale |
| `clinical` | Clinical findings, biopsy recommendation, procedure fit, and contraindications |
| `ct` | Nodule location, size, characteristics, Lung-RADS, suspicion, and biopsy recommendation |
| `labs` | Coagulation and laboratory suitability for an invasive procedure |
| `pft` | FEV1, DLCO, pulmonary suitability, and contraindications |

The decision rules then combine those extracted facts: CT or clinical notes can support suspicion and tissue sampling; the request or clinical notes can support procedure fit; both labs and PFT must support preliminary suitability. All four rules must pass, with no blocking issue, for `APPROVE`. A missing role, identity mismatch, or unsupported rule leads to `MANUAL_REVIEW`. Use a separate case JSON and output path for each PDF packet so each run has its own result.

For example, the included alternate packet maps five different synthetic PDFs in [`ai/alternate_case/case.json`](ai/alternate_case/case.json) and writes its result to [`ai/alternate_case/result.json`](ai/alternate_case/result.json).

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
