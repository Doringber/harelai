"""Gradio entry point for local use and Hugging Face Spaces."""
import os
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
import gradio as gr
from approval.core.models import Result
from approval.ui.service import saved_case, execute_case, evidence_rows, live_ready, SCENARIOS, ROOT
from approval.ui.views import overview, source_view, CSS

def payload(result):
    choices = [(f"{o.field} · {o.evidence.document_id} · {o.evidence.page}", str(i)) for i,o in enumerate(result.observations)]
    data = result.model_dump(mode="json")
    return (data, overview(result), evidence_rows(result), gr.Dropdown(choices=choices,value="0" if choices else None),
        source_view(result,0), [[i.severity,i.code,i.detail] for i in result.issues], data,
        [[t.get("stage"),t.get("document_id"),t.get("status"),str(t.get("cached","—")),t.get("seconds",0)] for t in result.trace])

def load_saved(scenario): return payload(saved_case(scenario))

def run_ui(scenario, live, ocr, *uploads, progress=gr.Progress()):
    progress(0, desc="Reading documents and checking evidence…")
    try:
        result = execute_case(scenario,live=live,uploads=list(uploads),ocr=ocr)
    except ValueError as exc:
        raise gr.Error(str(exc)) from None
    except Exception:
        raise gr.Error("The run could not complete. Check server configuration and input files.") from None
    progress(1, desc="Analysis complete")
    return payload(result)

def inspect_source(data, index): return source_view(Result.model_validate(data),index)
def filter_evidence(data, query): return evidence_rows(Result.model_validate(data),query)

def build_app():
    default_scenario = "Groq recorded run" if "Groq recorded run" in SCENARIOS else "Complete case"
    first = saved_case(default_scenario)
    ready = live_ready()
    with gr.Blocks(title="Evidence Review · Prior Authorization",delete_cache=(3600,3600)) as demo:
        state = gr.State(first.model_dump(mode="json"))
        gr.HTML('<div id="masthead"><span class="eyebrow">MEDICAL DOCUMENT REVIEW / ASSIGNMENT DEMO</span><h1>Every decision starts with evidence.</h1><p>Inspect the findings, trace each source, and review the four authorization conditions.</p></div>')
        gr.Markdown("**Fictional demo case.** Every result names its extraction method. Browsing saved results makes no provider call.")
        with gr.Row():
            scenario = gr.Dropdown(choices=list(SCENARIOS),value=default_scenario,label="Demonstration scenario",scale=3)
            load = gr.Button("View saved result",scale=1)
            rerun = gr.Button("Run local baseline",variant="primary",scale=1)
        summary = gr.HTML(overview(first))
        with gr.Tabs():
            with gr.Tab("Evidence"):
                search = gr.Textbox(label="Filter verified evidence",placeholder="Try FEV1, tissue, or a document name…")
                evidence = gr.Dataframe(value=evidence_rows(first),headers=["Field","Value","Document","Page / segment","Exact quote"],datatype=["str","str","str","number","str"],interactive=False,wrap=True)
                source = gr.Dropdown(choices=[(f"{o.field} · {o.evidence.document_id} · {o.evidence.page}",str(i)) for i,o in enumerate(first.observations)],value="0",label="Inspect a source")
                source_html = gr.HTML(source_view(first,0))
            with gr.Tab("Review notes"):
                issues = gr.Dataframe(value=[[i.severity,i.code,i.detail] for i in first.issues],headers=["Severity","Code","Explanation"],interactive=False,wrap=True)
                gr.Markdown("A warning is retained for review. A blocking issue prevents approval. Missing information is never treated as normal.")
            with gr.Tab("Full JSON"):
                raw = gr.JSON(value=first.model_dump(mode="json"),label="Complete result and provenance",open=False)
            with gr.Tab("Execution trace"):
                trace = gr.Dataframe(value=[[t.get("stage"),t.get("document_id"),t.get("status"),str(t.get("cached","—")),t.get("seconds",0)] for t in first.trace],headers=["Stage","Document","Status","Cached","Seconds"],interactive=False)
            with gr.Tab("Live AI analysis"):
                gr.Markdown("**Ready for live AI**" if ready else "**Live AI is disabled.** Configure the model and app login in server secrets to enable it. The demo remains usable without an API key.")
                gr.Markdown("Leave all uploads empty to analyze the fictional demo. Otherwise supply documents by role; missing roles lead to manual review. Uploaded content is sent to the configured model provider when you run analysis.")
                with gr.Row():
                    request_file = gr.File(label="Authorization request",file_types=[".pdf",".docx",".txt"],interactive=ready)
                    clinical_file = gr.File(label="Clinical notes",file_types=[".pdf",".docx",".txt"],interactive=ready)
                with gr.Row():
                    ct_file = gr.File(label="CT report",file_types=[".pdf",".docx",".txt"],interactive=ready)
                    labs_file = gr.File(label="Laboratory results",file_types=[".pdf",".docx",".txt"],interactive=ready)
                    pft_file = gr.File(label="Pulmonary function tests",file_types=[".pdf",".docx",".txt"],interactive=ready)
                ocr = gr.Checkbox(label="Use OCR on unreadable PDF pages (English)",value=False,interactive=ready)
                live = gr.Button("Run AI analysis",variant="primary",interactive=ready)
                gr.Markdown("The server limits live runs to 3 per process by default. Failed attempts also count. This is a run cap, not a guaranteed dollar budget.")
        outputs=[state,summary,evidence,source,source_html,issues,raw,trace]
        load.click(load_saved,[scenario],outputs,api_name=False)
        rerun.click(lambda s: run_ui(s,False,False),[scenario],outputs,concurrency_limit=1,concurrency_id="analysis",api_name=False)
        live.click(lambda s,o,*f:run_ui(s,True,o,*f),[scenario,ocr,request_file,clinical_file,ct_file,labs_file,pft_file],outputs,concurrency_limit=1,concurrency_id="analysis",api_name=False)
        source.change(inspect_source,[state,source],source_html,api_name=False)
        search.change(filter_evidence,[state,search],evidence,api_name=False)
        gr.Markdown("Assignment prototype · Recommendations follow the supplied qualitative rules. Model extraction is not deterministic; the decision function is deterministic for the same validated facts.")
    return demo

if __name__ == "__main__":
    username,password=os.getenv("APP_USERNAME"),os.getenv("APP_PASSWORD")
    if bool(username) != bool(password): raise RuntimeError("Set both APP_USERNAME and APP_PASSWORD")
    build_app().queue(max_size=8).launch(server_name=os.getenv("GRADIO_SERVER_NAME","0.0.0.0" if os.getenv("SPACE_ID") else "127.0.0.1"),
        server_port=int(os.getenv("PORT","7860")),auth=(username,password) if username else None,
        css=CSS,theme=gr.themes.Soft(primary_hue="teal",neutral_hue="slate"),
        max_file_size="20mb",blocked_paths=[str(ROOT/"examples"),str(ROOT/".env")],show_error=False)
