---
title: Evidence Review
emoji: 🔎
colorFrom: teal
colorTo: blue
sdk: gradio
sdk_version: 6.29.1
python_version: '3.12'
app_file: app.py
pinned: false
---

# Evidence Review

A prior-authorization assignment demo with an explicit decision policy, attributed observations and review notes. The bundled case is authored fictional data. The original assignment PDFs and their patient information are not included in this deployment.

The default demo needs no model key. It offers two saved local-baseline runs (complete case and missing lab report), a recorded Groq run when present, and a fresh local rerun. Each result is labeled with its extraction mode. A local baseline is not an AI result.

## Enable Groq

In Space Settings, add these secrets/variables:

| Name | Value |
|---|---|
| GROQ_API_KEY | Your private API key |
| GROQ_MODEL | openai/gpt-oss-120b |
| LLM_PROVIDER | groq |
| ENABLE_LIVE | 1 |
| APP_USERNAME | Choose an app login name |
| APP_PASSWORD | Choose a strong app password |
| MAX_LIVE_RUNS | 3 |

Authentication protects the entire app when configured. Live extraction is disabled server-side unless both credentials and app authentication are configured. Requests use the official Groq SDK, strict JSON-schema output, no streaming, temperature 0, and medium reasoning effort. A schema guarantee does not guarantee factual correctness; source validation and the deterministic decision function remain separate.

For Claude instead, set `LLM_PROVIDER=claude`, `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`; keep app authentication and `ENABLE_LIVE=1`.

A live run with uploads sends their extracted text to the chosen model provider. Limit runs to non-sensitive or explicitly authorized demonstration inputs. Documents are processed in isolated temporary workspaces; Gradio upload cache expires on an hourly cleanup schedule. The app is a single-user demonstration, not a multi-tenant clinical service.

The run cap is per process and resets on restart; it is not a durable dollar budget. Configure provider-side spending limits separately. Public demo browsing makes no model calls. Free Space hardware can sleep and has nonpersistent local storage.

## Local use

```bash
python -m pip install -r requirements.txt
python app.py
```

Open the local URL printed by Gradio. Full case results can also be generated through the CLI:

```bash
python -m approval.cli demo/case.json --extractor local
python -m approval.cli demo/case.json --extractor groq
```

No model key is included in this repository. No external medical knowledge or vector database is used to determine approval.
