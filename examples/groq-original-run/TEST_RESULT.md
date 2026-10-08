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
