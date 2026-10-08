"""Offline evidence viewer. All document-derived HTML is escaped."""
from html import escape

def render(result):
    e = lambda value: escape(str(value))
    criteria = "".join(f"<li><b>{'PASS' if c.met else 'REVIEW'}</b> {e(c.name)}</li>" for c in result.recommendation.criteria)
    facts = "".join(f"<tr><td>{e(o.field)}</td><td>{e(o.value)}</td><td>{e(o.evidence.document_id)} · {o.evidence.page}</td><td><details><summary>View evidence</summary><blockquote dir='auto'>{e(o.evidence.quote)}</blockquote></details></td></tr>" for o in result.observations)
    issues = "".join(f"<li><b>{e(i.severity)} / {e(i.code)}</b>: {e(i.detail)}</li>" for i in result.issues)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prior authorization evidence review</title><style>
body{{font:16px/1.6 system-ui,sans-serif;color:#193246;background:#f4f7fa;margin:0}}main{{max-width:1150px;margin:40px auto;padding:24px}}h1{{font-size:34px}}.meta{{color:#526477}}.status{{font-size:24px;font-weight:700;color:#17675b}}section{{background:white;padding:24px;margin:24px 0;border:1px solid #dce5ed;border-radius:12px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #ddd;vertical-align:top;overflow-wrap:anywhere}}blockquote{{margin:10px 0;white-space:pre-wrap}}summary{{cursor:pointer;color:#136b93}}.scroll{{overflow:auto}}
</style><main><p class="meta">ASSIGNMENT PROTOTYPE · EVIDENCE REVIEW</p><h1>Prior authorization review</h1>
<p class="meta">Run {e(result.run_id)} · {e(result.extraction_mode)} · {e(result.run_status)}</p>
<section><p class="status">{e(result.recommendation.status)}</p><p>{e(result.recommendation.reason)}</p><ul>{criteria}</ul></section>
<section><h2>Review notes</h2><ul>{issues}</ul><p>Conflicting values remain visible below; the summary selects the first observation and is not a conflict resolution.</p></section>
<section><h2>Facts and source evidence</h2><div class="scroll"><table><thead><tr><th>Field</th><th>Value</th><th>Document / page or segment</th><th>Source</th></tr></thead><tbody>{facts}</tbody></table></div></section>
<p class="meta">Task-specific recommendation support. No insurer submission or clinical clearance is performed.</p></main></html>"""
