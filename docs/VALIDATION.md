# Validation record

Executed in the supplied workspace with Python 3.12 and Pydantic 2.13.5.

- 26 unittest tests passed. They cover the supplied case and expected fields; grounding of every quote; absent condition; missing document/file; identity conflict; documented contraindication; cache reuse; fabricated/wrong-page/numeric evidence; Unicode and corrupt text; schema typing; bounded retries; non-retryable failures; structured Claude request construction; one schema repair; truncation; cache identity separation; DOCX tables; UTF-16; blank PDF; mocked OCR success/failure; and HTML escaping.
- Actual local end-to-end run on all five provided PDFs completed with APPROVE. Generated JSON/HTML are included and marked as the local baseline.
- Actual Tesseract integration smoke test: a PDF containing only a raster image of a generated line was OCR-processed, returned usable text, and preserved FEV1 62% and DLCO 58%. This does not establish OCR accuracy on a clinical corpus.
- Live Claude API execution has not been performed. Provider tests use controlled simulated responses; no model-quality, latency or token-cost claim is made.
- Native multilingual text handling is tested. Hebrew/Arabic OCR language packs and complex PDF tables have not been validated end to end.
- Dependency ranges are specified but not a reproducible cross-platform lockfile. Linux/macOS fresh-environment installation remains a user-side validation step.

- HTML source escaping was tested. A browser screenshot check could not run because the environment lacks the Playwright Chromium executable; visual browser QA remains pending.

## Version 0.2 verification

- 41 regression tests cover the original core plus the UI service, fictional complete/missing-document cases, source highlighting, evidence filtering, server-side live gating, process run cap and Groq structured request/refusal/truncation behavior.
- Gradio 6.29.1 was installed and its actual server returned HTTP 200 for the home page and configuration. The saved-result callback returned APPROVE; a fresh missing-labs run returned MANUAL_REVIEW.
- A real Groq SDK connectivity call to openai/gpt-oss-120b succeeded (95 total tokens).
- Sending the original medical PDFs to Groq was blocked by automatic approval review pending explicit authorization for that data transfer.
- Visual browser QA remains pending: the browser executable download failed; the server and callbacks were tested instead. Hugging Face browser navigation was interrupted, so no hosted Space was created.

- A complete live Groq run on the authored fictional case returned MANUAL_REVIEW due to omitted fields and equivalent Lung-RADS strings. That first run is retained as `demo/groq-first-review.json`.
- After explicit field instructions and a tested deterministic normalization of equivalent Lung-RADS category labels, a second complete live Groq run returned APPROVE. All source quotations passed grounding validation. It used 11,753 total tokens across five document calls. The full response is `demo/groq-live.json`, available as the default recorded run in the UI.
- Neither live run used the original assignment medical files. Both used the authored fictional text documents only.

## Original assignment documents: live Groq test, 2026-10-08

Following user authorization, all five original assignment PDFs were parsed locally and their extracted text was submitted to Groq (openai/gpt-oss-120b, extract-v2). SHA-256 comparisons confirmed these inputs match the uploaded originals. The assignment DOCX was not sent.

- Result: partial execution, MANUAL_REVIEW. This does **not** pass the expected APPROVE case.
- 72 observations were accepted by the current quote/numeric validation. Accepted does not establish semantic correctness: the audit below found field-mapping errors despite authentic quotations.
- Correctly extracted examples: SUVmax 4.2, Brock 68%, Mayo 71%, FEV1 62%, DLCO 58%, and Lung-RADS 4B.
- Two quoted spans could not be found verbatim in their cited pages (clinical rationale and PFT finding); they were rejected.
- Lab extraction exhausted bounded retries with TransientFailure. The result currently retains only the exception type, so the exact HTTP status cannot be established from this run. Do not label this specifically a rate-limit failure without further evidence.
- Semantic errors: Medicare MBI was labeled MRN on the request; historical visit/exam dates were labeled requested_date; the CT examination was labeled as the requested procedure. These produced blocking conflicts. They are extraction errors, not established contradictions in the original documents.
- Procedure wording also differs between authentic mentions; string-based conflict checking needs scoped normalization after fixing extraction field meanings.
- Age discrepancy and secondary-source PET remain warnings.
- Successful responses reported 17,655 tokens total. This excludes any usage not returned by failed requests and is not a billing estimate.
- All 41 existing regression tests passed. These tests did not catch the live semantic extraction errors, demonstrating that passing unit tests alone is insufficient.

Recorded JSON and source-viewable HTML: `examples/groq-original-run/result.json` and `examples/groq-original-run/report.html`.

Required next fixes: tighten identifier/date/procedure semantics in extraction; retain sanitized provider error codes and failed-attempt usage; add regression cases for the observed mapping errors; perform a bounded fresh verification after fixes. Do not weaken citation validation or force APPROVE.

This recorded original-data run is kept outside `space-ready/` and the public demo. The API token is not included. No hosted deployment was created by this test.
