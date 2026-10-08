from html import escape
from approval.core.models import Result

def overview(result: Result):
    e = lambda x: escape(str(x))
    approved = result.recommendation.status == "APPROVE"
    mode = ("Live Groq extraction" if result.extraction_mode.startswith("groq:") else "Live Claude extraction") if result.extraction_mode.startswith(("claude:","groq:")) else "Local baseline · no model call"
    metrics = [("DOCUMENTS", len(result.documents)), ("EVIDENCE RECORDS", len(result.observations)),
        ("CONDITIONS MET", f"{sum(c.met for c in result.recommendation.criteria)}/4"), ("RUN STATUS", result.run_status)]
    cards = "".join(f'<div class="metric"><span>{e(k)}</span><strong>{e(v)}</strong></div>' for k,v in metrics)
    criteria = "".join(f'<div class="criterion"><span class="mark {"pass" if c.met else "review"}">{"✓" if c.met else "!"}</span><div><b>{e(c.name)}</b><small>{len(c.evidence)} source references</small></div></div>' for c in result.recommendation.criteria)
    return f'<div class="result-banner"><div><span class="eyebrow">RECOMMENDATION</span><h2>{"Approve" if approved else "Manual review"}</h2></div><span class="mode">{e(mode)}</span></div><p class="reason">{e(result.recommendation.reason)}</p><div class="metrics">{cards}</div><div class="criteria">{criteria}</div>'

def source_view(result, index):
    e = lambda x: escape(str(x))
    if not result.observations: return '<p>No verified evidence is available.</p>'
    try: o = result.observations[int(index)]
    except (ValueError, TypeError, IndexError): return '<p>Select a field to inspect its evidence.</p>'
    d = next(d for d in result.documents if d.id == o.evidence.document_id)
    p = next(p for p in d.pages if p.number == o.evidence.page)
    text = e(p.text)
    quote = e(o.evidence.quote)
    if quote in text: text = text.replace(quote, '<mark>'+quote+'</mark>', 1)
    return f'<div class="source-head"><b>{e(o.field)}</b><span>{e(d.filename)} · page / segment {p.number} · {e(p.method)}</span></div><blockquote dir="auto">{quote}</blockquote><details><summary>Read the full extracted page</summary><pre dir="auto">{text}</pre></details>'

CSS = """
.gradio-container {max-width:1200px !important; margin:auto !important; font-family:Inter,ui-sans-serif,system-ui,sans-serif !important}
#masthead {padding:28px 0 18px;border-bottom:1px solid #dbe4ec;margin-bottom:18px}
#masthead h1 {font-size:34px;letter-spacing:-1px;margin:5px 0;color:#183346}
#masthead p {color:#577184;margin:8px 0}
.eyebrow {font-size:11px;letter-spacing:1.7px;color:#547588;font-weight:700}
.result-banner {display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:8px}
.result-banner h2 {font-size:30px;color:#165c54;margin:6px 0}
.mode {padding:7px 12px;background:#edf3f7;color:#395569;border-radius:20px;font-size:12px}
.reason {line-height:1.7;color:#37546a}
.metrics {display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}
.metric {padding:18px;background:#f3f7fa;border:1px solid #e1e9ef;border-radius:10px}
.metric span {display:block;font-size:10px;color:#617b8c;letter-spacing:1px}
.metric strong {display:block;font-size:22px;color:#234459;margin-top:7px}
.criteria {display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
.criterion {display:flex;align-items:center;gap:12px;border:1px solid #e1e9ef;border-radius:10px;padding:16px;color:#27465a}
.criterion small {display:block;color:#6b8392;margin-top:4px}
.mark {border-radius:50%;padding:4px 10px;font-weight:bold}.pass {background:#e0f2e9;color:#1d7153}.review {background:#fff0d3;color:#875e0d}
.source-head {display:flex;flex-direction:column;gap:6px;color:#27465a}.source-head span {font-size:12px;color:#648091}
blockquote {background:#f1f7fa;border-left:3px solid #399786;padding:18px;margin:18px 0;white-space:pre-wrap;color:#294f61}
pre {white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.7} mark {background:#fff0a8;color:#183346}
@media(max-width:650px){.metrics,.criteria{grid-template-columns:1fr 1fr}.result-banner{align-items:flex-start;flex-direction:column}.criterion{padding:10px}.metric{padding:10px}#masthead h1{font-size:27px}}
"""
