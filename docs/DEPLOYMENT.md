# Gradio demo and Hugging Face deployment

## Start locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

The default UI opens on port 7860. It displays fictional saved cases, a fresh local baseline run, field filtering, highlighted source excerpts, review notes, full JSON and execution trace. No key is needed for the demo. Uploaded documents require live AI; the local regex baseline is deliberately not offered as a general-purpose upload analyzer.

## Deploy a private Space

The package includes a `space-ready` folder with only application code and fictional data. Do not upload the entire project, because `examples/` contains the supplied original assignment PDFs.

Either create a private Gradio Space and upload the **contents** of `space-ready`, or use:

```bash
hf auth login
python scripts/deploy_space.py --repo YOUR_USERNAME/evidence-review
```

The helper uses your existing Hugging Face login, creates an owner-private Space if necessary, and uploads only a generated allowlist of files. It never uploads model keys. Publishing to an audience and entering secrets remain explicit account settings. A private Space is not automatically accessible to an external reviewer.

To create a clean folder yourself:

```bash
python scripts/prepare_space.py /tmp/evidence-review-space
```

The destination must not already exist. See `SPACE_README.md` for exact Groq/app-login settings. In a hosted Space, the application automatically binds to `0.0.0.0`.

## Groq setup

Set `GROQ_API_KEY` in a shell or Space secret, `GROQ_MODEL=openai/gpt-oss-120b`, `LLM_PROVIDER=groq`, `ENABLE_LIVE=1`, `APP_USERNAME` and `APP_PASSWORD`. Do not put actual values in source control. `MAX_LIVE_RUNS=3` is a process-local guard; restarts reset it. The CLI does not enforce this UI run cap.

For the original assignment documents, run locally:

```bash
python -m approval.cli examples/case.json --extractor groq --output output/groq
```

The live adapter is non-streaming so that partial JSON never reaches the policy engine. Structured-output mode and application validation guard shape and grounding. They do not eliminate extraction errors. No automatic fallback substitutes local output for failed AI output.

## Scope and limitations

The app is a single-user demo with a small queue and one analysis at a time. SQLite checkpoints are scoped to each UI execution and are deleted with its temporary workspace; UI runs do not share a persistent cross-session cache. The CLI retains its original checkpoint/resume behavior. Saved demo viewing avoids all model calls.

No hosted Space was published from the development environment. Browser navigation to Hugging Face did not complete. Use the prepared folder or deploy helper after authenticating your account.
