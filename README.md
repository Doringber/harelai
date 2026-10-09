# Medical prior authorization review (local AI)

Reads the five supplied medical documents for a robotic-assisted lung biopsy request and returns
**APPROVE** or **MANUAL_REVIEW** with a reason. The AI runs locally with [Ollama](https://ollama.com),
so no document leaves your machine and no API key is needed.

## How to run

Requires Python 3.11+ and Ollama.

```bash
ollama pull gemma4                      # once, ~10 GB
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m approval                      # reads case.json, writes result.json (~1.5 min)
pytest tests -q                         # 11 tests, no Ollama needed
```

Options: `python -m approval my_case.json --model qwen3-coder:30b --output out.json`.
`case.json` lists each document and its role (`request`, `clinical`, `ct`, `labs`, `pft`).

## Output for the supplied case

The full output is in [`result.json`](result.json). It starts with the required fields:

```json
{
  "case_id": "PA-2025-847291",
  "patient": { "name": "Margaret A. Johnson", "date_of_birth": "1952-03-15", "mrn": "847291" },
  "request": {
    "procedure": "Robotic-Assisted Transbronchial Lung Biopsy",
    "cpt_codes": ["31629", "31632", "77012"],
    "requested_date": "2025-12-10",
    "provider": "David Chen, MD",
    "diagnoses": ["R91.1", "F17.211", "J44.9", "Z77.22"],
    "facility": "UC Davis Medical Center, Sacramento, CA"
  },
  "clinical_summary": {
    "finding": "Suspicious right upper lobe pulmonary nodule",
    "nodule_size": "18 x 15 mm",
    "lung_rads": "4B",
    "suv_max": 4.2,
    "fev1_percent": 62,
    "dlco_percent": 58,
    "coagulation_status": "Normal",
    "location": "right upper lobe, posterior segment",
    "malignancy_risk": "68%",
    "...": "..."
  },
  "recommendation": {
    "status": "APPROVE",
    "reason": "The clinical findings support tissue diagnosis of a suspicious right upper lobe pulmonary nodule (Lung-RADS 4B), and the requested procedure is appropriate based on the lesion location and the patient's COPD (FEV1 62% predicted)."
  }
}
```

After these come `rules` (each rule met or not), `issues` (anything that needs attention) and `evidence`
(the exact sentence each value was taken from).

## How the recommendation is made

The model only reads. Plain code checks its answers and makes the decision.

1. **Read** each PDF into text (`approval/read.py`).
2. **Extract** (`approval/extract.py`). Each document type has a short list of fields. The local model is
   asked **one field at a time**, and must return the value plus an exact quote from the document,
   or `found: false`.
3. **Check** (`approval/check.py`):
   - the quote must really appear in the document, and a number must appear in its quote. Otherwise the
     answer is dropped;
   - all five documents must be present and name the same patient (name, date of birth, MRN);
   - dates are converted to one format in code; the model's date format is not trusted.
4. **Decide** (`approval/decide.py`). APPROVE only when all four assignment rules hold:

   | Rule | Proven by |
   |---|---|
   | Suspicious nodule requiring investigation | CT report or clinical notes |
   | Tissue sampling recommended | CT report or clinical notes |
   | Requested procedure fits the findings and the patient | request form or clinical notes |
   | Preliminary tests show no clear barrier | lab report **and** PFT report |

   Anything else is MANUAL_REVIEW: a rule not proven, a stated contraindication, a missing document,
   a different patient, or a dropped answer that argued against approval. A rule counts as met only when
   a document says so in words, so there are no invented medical thresholds for FEV1 or SUV.
   There is no rejection path, as the assignment requested.

## Limits and what I would improve with more time

- **Tested on one case.** Three runs of the supplied case all returned APPROVE with no issues. With the
  lab report's "suitable for invasive procedures" sentence removed, it returned MANUAL_REVIEW on
  "Preliminary tests show no clear barrier", as it should. That doesn't prove it works on other cases.
  *Next:* a small evaluation set (missing documents, contradictions, contraindications), measuring
  accuracy per field.
- **A real quote is not proof of meaning.** The check confirms the quote exists, not that it supports
  the value.
  *Next:* a second check (another model or rules) on the decision-critical fields.
- **Text PDFs only.** Scanned PDFs are reported and stop approval; there is no OCR.
- **Speed.** One question per call takes about 1.5 minutes per case on a laptop.
  *Next:* group the easy fields into one call.
- **Not a clinical system.** It supports a human reviewer for this assignment; it is not a validated
  medical or insurance decision.
