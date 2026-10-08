# Next steps

## Required to complete the AI submission

1. Configure `ANTHROPIC_API_KEY` and an exact `ANTHROPIC_MODEL` locally. Run the documented Claude command on the five inputs.
2. Inspect `output/claude/result.json` and the evidence viewer. Verify every requested field, pre/post bronchodilator distinctions, CPT strings and all four condition citations. Review semantic correctness, not only a passing JSON schema.
3. Keep that live run's JSON with model identity and trace as the actual AI submission output. Do not rename the local baseline run to imply it used Claude.
4. Expand the evaluator with altered/contradictory cases and independently labeled expected findings before making reliability claims.

## Optional extensions discussed

- A richer local upload/review UI with original-page navigation and evidence bounding boxes. The current viewer is generated HTML with expandable quotes.
- A separate term-explanation service with an allowlist of authoritative sources, caching, refresh dates and cited Hebrew explanations. It must never contribute patient facts or override policy. Dynamic glossary retrieval is not implemented in this first slice.
- More robust PDF structure/table recovery (evaluate Docling or another adapter), visual/native-text comparison, mixed-page OCR and layout regression corpus. The current quality heuristic cannot detect every hidden-layer, white-on-white or scrambled-font problem.
- An independently optional extraction verifier with measured benefit. No Jev dependency or second-model verification is currently implemented.
- A single-flight/lease mechanism if multiple workers become an actual requirement. Current SQLite transactions protect writes but do not prevent duplicate in-flight model calls.
- Provider request IDs, aggregate token/cost accounting, detailed retry tracing, a hard whole-run deadline, structured semantic error codes and a tested dependency lockfile.

## Inputs needed from Dor

Only the local API key and exact model ID are needed for the remaining live run. Do not put the key in chat or source control. A repository URL is needed only if you want the source pushed to your Git account. A deadline or additional evaluator restrictions may change the priority of optional UI/glossary work.
