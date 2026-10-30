"""New Oct 27: standalone judge-facing case report from an evaluator receipt.

This page is a playback artifact; the private truth shown after 'Reveal' has not
been supplied to the model. The HTML is not evidence that an API call was live.
"""
from __future__ import annotations
from html import escape
import json


def _safe(x: object) -> str:
    return escape(str(x), quote=True)


def _json(x: object) -> str:
    return _safe(json.dumps(x, sort_keys=True, indent=2))


def render_html(r: dict) -> str:
    p = r["case_public"]
    receipts = r.get("evidence_receipts", [])
    mode = "LIVE META TOOL INVESTIGATION" if r.get("mode") == "meta" else "OFFLINE DETERMINISTIC REPLAY"
    actions = "".join(
        '<div class="probe"><div class="small">PROBE ' + _safe(i + 1) + '</div>'
        '<strong>' + _safe(e.get("probe_id")) + '</strong> · cost ' + _safe(e.get("cost")) +
        '<pre>' + _json(e.get("evidence")) + '</pre></div>'
        for i, e in enumerate(receipts)
    ) or '<p>No independent readback was obtained.</p>'
    calls = "".join(
        '<li>' + _safe(e.get("tool")) +
        (' — ' + _safe(e.get("probe")) if e.get("probe") else '') +
        (' — accepted' if e.get("accepted") else ' — rejected') + '</li>'
        for e in r.get("tool_calls", [])) or '<li>Offline demo; no AI tool calls</li>'
    verdict = r.get("claimed_status", "INCONCLUSIVE")
    color = {"VERIFIED": "#16a34a", "FAILED": "#dc2626", "INCONCLUSIVE": "#c18418"}.get(verdict, "#64748b")
    proof = r.get("receipt_chain", [])
    last_hash = proof[-1]["sha256"] if proof else "No observations"
    # Truth is included only in the FINAL judge-facing report, never the API prompt.
    truth = _safe(r.get("true_status", "Unknown"))
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StateProof · Evidence Investigation</title>
<style>
:root{{--ink:#15202f;--muted:#64748b;--paper:#f8fafc;--line:#d8e0e9}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:38px 24px}}h1{{font-size:35px;margin:10px 0}}h2{{font-size:21px;margin:0 0 12px}}
.small{{font-size:12px;letter-spacing:.1em;color:var(--muted);text-transform:uppercase}}
.lead{{font-size:19px;max-width:760px;color:#475569}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:24px 0}}
.card{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:22px;min-width:0}}
.flag{{font-size:22px;font-weight:700;color:{color}}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f9;padding:14px;border-radius:8px;font:13px/1.55 ui-monospace,monospace}}
.probe{{padding:14px;border-left:3px solid #4f46e5;margin:12px 0;background:#f8fafc;border-radius:6px}}
button{{background:#15202f;color:white;padding:12px 18px;border:0;border-radius:8px;font-weight:600;cursor:pointer}}
footer{{color:var(--muted);font-size:13px;margin-top:30px}}code{{font-size:13px;overflow-wrap:anywhere}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}}h1{{font-size:28px}}}}
</style></head><body><main>
<div class="small">Meta Global AI Developer Hackathon · { _safe(mode) } · synthetic simulation</div>
<h1>Agent said success. What really happened?</h1>
<p class="lead">An agent's completion message is not a guarantee. An independent readback decides what we can prove.</p>
<div class="grid">
<section class="card"><div class="small">Agent claim</div><h2>SUCCESS</h2>
<p><strong>Contract:</strong> {_safe(p.get('contract'))}</p>
<p><strong>Case:</strong> {_safe(p.get('case_id'))}</p><p><strong>Evidence budget:</strong> {_safe(p.get('budget'))}</p></section>
<section class="card"><div class="small">Evidence-gated result</div><div class="flag">{_safe(verdict)}</div>
<p>Independent deterministic gate: <strong>{_safe(r.get('gate_supported_status'))}</strong></p>
<p>Probe cost: {_safe(r.get('cost'))} · Supported: {_safe(r.get('gate_accepted'))}</p>
<p>Model explanation: {_safe(r.get('model_explanation'))}</p></section>
</div>
<div class="grid"><section class="card"><h2>Investigation evidence</h2>{actions}</section>
<section class="card"><h2>Decision timeline</h2><ol>{calls}</ol><p class="small">Termination: {_safe(r.get('termination'))}</p>
<p><strong>Ungrounded submissions rejected:</strong> {_safe(len(r.get('rejected_claims', [])))}</p>
<p><strong>Input / output tokens:</strong> {_safe(r.get('api_usage', {}).get('input_tokens',0))} / {_safe(r.get('api_usage', {}).get('output_tokens',0))}</p></section></div>
<section class="card"><h2>Independent audit trail</h2><p>This local SHA-256 chain detects accidental receipt changes; it is <strong>not</strong> a signed or externally authenticated record.</p>
<p class="small">Final observation SHA-256</p><code>{_safe(last_hash)}</code><hr>
<details><summary><strong>Reveal private evaluator truth (not sent to Muse)</strong></summary>
<p>Hidden outcome: <strong>{truth}</strong></p><p>Correct vs truth: {_safe(r.get('correct_vs_truth'))}</p>
<p>This was a synthetic test; do not treat it as a production transaction or generalized accuracy claim.</p>
</details></section>
<footer>Generated from a single local, reproducible experiment receipt. { _safe(r.get('project_component','')) }.</footer>
</main></body></html>'''
