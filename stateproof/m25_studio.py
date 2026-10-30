"""StateProof M2.5: local interactive evidence-investigation studio (Oct 29 build).

No model calls on page load. All services remain local and synthetic.
Earlier M2.3 simulation is a disclosed October 26 prebuild dependency.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
from threading import Lock
from urllib.parse import urlparse
from .evidence_game import Episode, baseline, cohort
from .m24_runner import run_index
from .m26_negative_control import run_negative_control


def public_cases():
    """Case metadata available to the investigator; never include private variants."""
    records = []
    for i, (case_id, case) in enumerate(cohort()):
        ep = Episode(case, case_id)
        try:
            p = ep.public_view()
            records.append({"index": i, "id": case_id, "workflow": p["workflow"],
                            "contract": p["contract"], "probes": p["probes"],
                            "budget": p["budget"], "agent_reported_status": p["agent_reported_status"],
                            "readback_access": p["readback_access"]})
        finally:
            ep.close()
    return records


def run_studio_case(index: int, mode: str, *, runner=run_index):
    if type(index) is not int or index not in range(len(cohort())):
        raise ValueError("Invalid case index")
    if mode not in ("offline", "meta"):
        raise ValueError("Invalid run mode")
    cid, case = cohort()[index]
    receipt = runner(index, mode=mode)
    if receipt.get("case_id") != cid:
        raise RuntimeError("Runner case ID mismatch")
    comparisons = {}
    for strategy in ("contract_aware", "cheap_first", "random"):
        _, result = baseline(case, cid, strategy, seed=20261027)
        comparisons[strategy] = {
            "status": result["claimed_status"], "cost": result["cost"],
            "grounded": result["grounded"],
            "correct_vs_truth": result["correct_vs_truth"],
            "probes": result["probes"],
        }
    return {"receipt": receipt, "baselines": comparisons, "synthetic": True,
            "comparison_warning": "One known synthetic case, not a blind benchmark or proof of superiority."}


_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StateProof Lab · Agent outcome verification</title><meta name="csrf-token" content="__CSRF__">
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#15263d;background:#f2f5fa}
*{box-sizing:border-box}body{margin:0}button,select{font:inherit}button{cursor:pointer}
header{background:#101f36;color:#fff;padding:18px max(24px,calc((100% - 1180px)/2));display:flex;justify-content:space-between;align-items:center;gap:12px}
.brand{font-weight:800;letter-spacing:-.04em;font-size:21px}.brand i{font-style:normal;color:#79cdfa}.pill{border:1px solid #45556d;border-radius:99px;padding:5px 10px;color:#bcd0e8;font-size:11px;letter-spacing:.12em;text-transform:uppercase}
main{max-width:1180px;margin:auto;padding:32px 24px 60px}h1{font-size:clamp(29px,4vw,49px);line-height:1.1;letter-spacing:-.05em;margin:4px 0 12px}.intro{max-width:800px;color:#56667c;font-size:17px;line-height:1.55;margin:0 0 24px}
label{display:block;font-size:12px;letter-spacing:.1em;color:#607189;text-transform:uppercase;font-weight:800;margin-bottom:8px}
.workspace{display:grid;grid-template-columns:330px minmax(0,1fr);gap:18px;align-items:start}.card{background:#fff;border:1px solid #dce4ee;border-radius:15px;padding:22px;box-shadow:0 8px 26px rgba(17,38,66,.035)}
.sidebar h2,.view h2{font-size:19px;margin:0 0 17px;letter-spacing:-.02em}select{width:100%;border:1px solid #cdd8e4;background:white;border-radius:9px;padding:11px;font-weight:650;color:#18304d}
.contract{font-size:14px;line-height:1.6;background:#f3f7fc;padding:12px;border-radius:9px;margin:15px 0;color:#374e69}.meta{display:flex;justify-content:space-between;color:#60738d;font-size:13px;margin:8px 0}.probe-list{display:flex;gap:7px;flex-wrap:wrap}.probe{font:12px ui-monospace,monospace;background:#e9f1fc;border-radius:7px;padding:5px 7px;color:#375478}
.primary,.secondary{width:100%;padding:13px;border-radius:9px;font-weight:800;margin-top:12px;border:1px solid #1d5ec8}.primary{background:#1d5ec8;color:white}.secondary{background:white;color:#1d5ec8}.primary:disabled,.secondary:disabled{opacity:.45;cursor:not-allowed}
.note{font-size:12px;line-height:1.55;color:#63758b;margin-top:13px}.hint{border-left:3px solid #4f93ef;padding-left:9px}
.statusline{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:15px}.stage{display:inline-block;padding:5px 10px;background:#edf3fb;border-radius:99px;font-size:11px;letter-spacing:.08em;font-weight:800;color:#53667f}
.hero{display:grid;grid-template-columns:1fr 1fr;gap:12px}.outcome{background:#f6f9fd;padding:20px;border:1px solid #e1eaf4;border-radius:12px}.outcome .big{font-size:28px;font-weight:800;letter-spacing:-.03em}.outcome small{color:#6a7890;font-weight:800;font-size:11px;letter-spacing:.12em;display:block;margin-bottom:8px}.success{color:#197953}.failed{color:#c52d3f}.inconclusive{color:#9b6f11}
.twin{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-top:15px}.audit{border:1px solid #dbe4ef;border-radius:13px;padding:16px}.audit h3{font-size:15px;margin:0 0 12px}.events{list-style:none;padding:0;margin:0}.events li{padding:9px 0;border-bottom:1px solid #e7edf5;font-size:13px;overflow-wrap:anywhere}.events li:last-child{border:0}.muted{color:#738198}.kv{display:flex;justify-content:space-between;border-bottom:1px solid #edf1f6;padding:8px 0;font-size:13px;gap:8px}.kv:last-child{border-bottom:0}pre{background:#f4f7fb;border-radius:8px;padding:10px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 ui-monospace,monospace}
.truth{background:#eef7f5;border-radius:10px;padding:12px;margin-top:12px;font-size:13px}.disclosure{background:#fff7e6;color:#825800;border-radius:10px;padding:11px;margin-top:13px;font-size:13px;line-height:1.5}
footer{margin-top:20px;color:#6c7c93;font-size:12px}.error{background:#fff1f1;color:#9c2933;padding:12px;border-radius:8px}.working{background:#ecf4ff;color:#1c5c9c;padding:12px;border-radius:8px}
@media(max-width:820px){.workspace{grid-template-columns:1fr}.hero,.twin{grid-template-columns:1fr}header{padding:15px 20px}}
</style></head><body>
<header><div class="brand">StateProof <i>Lab</i></div><div class="pill">Meta AI Hackathon · synthetic lab</div></header>
<main><div class="stage">Interactive investigator · October 29 build</div><h1>Agent said success.<br>Can we prove it?</h1>
<p class="intro">Choose a workflow, let Muse Spark collect independent evidence, and see a deterministic gate decide what the evidence actually supports. No real financial transactions or production systems.</p>
<div class="workspace"><section class="card sidebar"><h2>01 · Choose a scenario</h2>
<label for="case">Synthetic case</label><select id="case"></select><div class="contract" id="contract">Loading cases…</div>
<div class="meta"><span>Evidence budget</span><strong id="budget">—</strong></div><label>Available readbacks</label><div id="probes" class="probe-list"></div>
<button id="offline" class="secondary" disabled>Replay deterministic gate (free)</button>
<button id="challenge" class="secondary" disabled>Challenge the evidence gate (free)</button>
<button id="live" class="primary" disabled>Investigate with Meta Muse</button>
<div class="note hint" id="livehint">Live calls are disabled unless explicitly enabled when starting the local server.</div>
<p class="note">Live mode uses promotional API credits. Each click runs one fresh synthetic investigation. No calls occur on page load.</p>
<p class="note">Gate challenge deliberately injects an unsupported SUCCESS claim offline. It is <strong>not</strong> a Muse mistake or a live experiment.</p></section>
<section class="card view"><div class="statusline"><h2>02 · Investigation</h2><span class="stage" id="stage">READY</span></div>
<div id="notice" class="note">Select a case, then run a replay or live investigation.</div>
<div class="hero" style="margin-top:17px"><div class="outcome"><small>AGENT CLAIM</small><div class="big">SUCCESS</div><p class="note">Reported by the simulated agent, not proof of external state.</p></div>
<div class="outcome"><small>INDEPENDENT EVIDENCE GATE</small><div class="big" id="verdict">NOT RUN</div><p class="note" id="gateNote">The gate accepts only evidence-supported conclusions.</p></div></div>
<div class="twin"><div class="audit"><h3>Evidence acquired</h3><ul id="readbacks" class="events"><li class="muted">No readbacks yet</li></ul></div>
<div class="audit"><h3>Model decisions</h3><ul id="timeline" class="events"><li class="muted">No tool calls yet</li></ul></div></div>
<div class="twin"><div class="audit"><h3>Same-case baseline comparison</h3><div id="baselines" class="note">Run an investigation to compare against fixed non-LLM strategies.</div></div>
<div class="audit"><h3>Experiment provenance</h3><div id="metrics" class="note">Mode, token usage, probe cost and receipts appear here.</div><div class="disclosure">These are small known synthetic cases. A matching result does not prove a model advantage over deterministic testing.</div></div></div>
<div id="revealArea" hidden><button class="secondary" id="reveal" type="button">Reveal private evaluator truth</button><div id="truth" class="truth" hidden></div><button class="secondary" id="download" type="button">Download JSON evidence receipt</button></div>
</section></div><footer>Local-only demonstration • No real payments, refunds, or deployments • Earlier M2.3 simulation is an Oct 26 prebuild dependency; M2.5 studio is separately authored Oct 29.</footer></main>
<script>
'use strict';
const csrf=document.querySelector('meta[name="csrf-token"]').content;
const $=id=>document.getElementById(id);
let cases=[], latest=null, enabled=false, remaining=0;
function item(parent,tag,content,cls){const el=document.createElement(tag);el.textContent=String(content);if(cls)el.className=cls;parent.appendChild(el);return el;}
function setVerdict(s){$('verdict').textContent=s;$('verdict').className='big '+(s==='VERIFIED'?'success':s==='FAILED'?'failed':'inconclusive');}
function clear(node){while(node.firstChild)node.removeChild(node.firstChild);}
function row(parent,label,val){const el=item(parent,'div','', 'kv');item(el,'span',label,'muted');item(el,'strong',val);}
function selected(){return cases.find(x=>x.index===Number($('case').value));}
function updateCase(){const x=selected();if(!x)return;$('contract').textContent=x.contract;$('budget').textContent=x.budget+' units';clear($('probes'));for(const p of x.probes)item($('probes'),'span',p.probe_id+' · '+p.cost,'probe');$('notice').textContent='Ready to investigate '+x.workflow+' ('+x.id+').';}
function busy(isBusy){$('offline').disabled=isBusy;$('challenge').disabled=isBusy;$('live').disabled=isBusy||!enabled||remaining<1;}
async function load(){try{const res=await fetch('/api/cases',{cache:'no-store'});if(!res.ok)throw Error('Unable to load cases');const data=await res.json();cases=data.cases;enabled=data.live_enabled;remaining=data.remaining_live_calls;clear($('case'));for(const c of cases){const opt=document.createElement('option');opt.value=c.index;opt.textContent='Case '+(c.index+1)+' · '+c.workflow+' · '+c.id;$('case').appendChild(opt);}$('case').value='3';$('case').onchange=updateCase;$('offline').disabled=false;busy(false);$('livehint').textContent=enabled?'Live Muse enabled · '+remaining+' call(s) remaining this server session.':'Live Muse disabled. Restart server with STATEPROOF_ENABLE_META=1 to enable explicitly.';updateCase();}catch(e){$('notice').textContent='Startup error: '+e.message;}}
async function run(mode){if(mode==='meta'&&!confirm('Make a paid Meta Model API investigation using your available credits?'))return;const x=selected();if(!x)return;busy(true);$('stage').textContent='RUNNING';$('notice').className='working';$('notice').textContent=mode==='meta'?'Muse is requesting independent evidence. The page will update after the investigation completes…':'Replaying deterministic evidence checks…';try{const response=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({case_index:x.index,mode})});const result=await response.json();if(!response.ok)throw Error(result.error||'Run failed');latest=result;remaining=result.remaining_live_calls;show(result);$('stage').textContent=mode==='meta'?'LIVE MUSE':'OFFLINE REPLAY';$('notice').className='note';$('notice').textContent=mode==='meta'?'Live Meta tool investigation completed.':'Deterministic replay completed without model calls.';}catch(e){$('stage').textContent='ERROR';$('notice').className='error';$('notice').textContent=e.message;}finally{busy(false);$('livehint').textContent=enabled?'Live Muse enabled · '+remaining+' call(s) remaining this server session.':'Live Muse disabled; offline mode is available.';}}
function show(data){const r=data.receipt;setVerdict(r.gate_supported_status||'INCONCLUSIVE');$('gateNote').textContent='Model: '+r.claimed_status+' · accepted: '+r.gate_accepted+' · probe cost: '+r.cost;clear($('readbacks'));for(const x of r.evidence_receipts||[]){const li=item($('readbacks'),'li',x.probe_id+' · cost '+x.cost);item(li,'pre',JSON.stringify(x.evidence,null,2));}if(!(r.evidence_receipts||[]).length)item($('readbacks'),'li','No independent readbacks obtained');clear($('timeline'));for(const x of r.tool_calls||[]){item($('timeline'),'li','Turn '+x.turn+' · '+x.tool+(x.probe?' ('+x.probe+')':'')+' · '+(x.accepted?'accepted':'rejected'));}if(!(r.tool_calls||[]).length)item($('timeline'),'li','Offline mode: no Meta tool calls');for(const x of r.rejected_claims||[])item($('timeline'),'li','Unsupported verdict rejected: '+x.requested);clear($('baselines'));row($('baselines'),r.mode==='meta'?'Muse':'Offline gate',r.claimed_status+' · cost '+r.cost);for(const [name,b] of Object.entries(data.baselines))row($('baselines'),name.replaceAll('_',' '),b.status+' · cost '+b.cost);clear($('metrics'));row($('metrics'),'Execution',r.mode==='meta'?'Live Meta':'Offline deterministic');row($('metrics'),'Tokens',(r.api_usage?.input_tokens||0)+' in / '+(r.api_usage?.output_tokens||0)+' out');row($('metrics'),'Rejections',(r.rejected_claims||[]).length);row($('metrics'),'Termination',r.termination);row($('metrics'),'Evidence record','Local JSON + SHA-256 chain');$('revealArea').hidden=false;$('truth').hidden=true;}
async function challengeGate(){
const x=selected();if(!x)return;
busy(true);$('stage').textContent='TESTING GATE';$('notice').className='working';$('notice').textContent='Submitting a deliberately unsupported verdict to the deterministic evidence gate (offline; zero Meta calls)…';
try{
const response=await fetch('/api/gate-challenge',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({case_index:x.index})});
const result=await response.json();if(!response.ok)throw Error(result.error||'Gate challenge failed');
latest=null;const r=result.control;
$('stage').textContent='OFFLINE NEGATIVE CONTROL';$('notice').className='note';$('notice').textContent='An intentionally unsupported candidate was rejected by the deterministic gate. This is not a Muse output.';
$('verdict').textContent='REJECTED';$('verdict').className='big failed';
$('gateNote').textContent='Attempted '+r.attempted_verdict+' · supported by available evidence: '+r.gate_supported_status+' · accepted: false';
clear($('readbacks'));for(const x of r.evidence_receipts||[]){const li=item($('readbacks'),'li',x.probe_id+' · cost '+x.cost);item(li,'pre',JSON.stringify(x.evidence,null,2));}
clear($('timeline'));item($('timeline'),'li','OFFLINE INJECTION: simulated VERIFIED candidate');item($('timeline'),'li','DETERMINISTIC GATE: rejected as unsupported');item($('timeline'),'li','Muse model calls: 0');
clear($('baselines'));row($('baselines'),'Negative control','REJECTED · cost '+r.probe_cost);item($('baselines'),'p','This tests gate enforcement, not fault-detection accuracy or model superiority.','note');
clear($('metrics'));row($('metrics'),'Execution','Offline negative control');row($('metrics'),'Model tokens','0');row($('metrics'),'Assertion rejected','Yes');row($('metrics'),'Evidence chain','Local SHA-256');
$('revealArea').hidden=true;
}catch(e){$('stage').textContent='ERROR';$('notice').className='error';$('notice').textContent=e.message;}finally{busy(false);}
}
$('challenge').onclick=challengeGate;
$('offline').onclick=()=>run('offline');$('live').onclick=()=>run('meta');$('reveal').onclick=()=>{if(!latest)return;const r=latest.receipt;$('truth').textContent='Private synthetic truth: '+r.true_status+' · model correct vs truth: '+r.correct_vs_truth+' · gate accepted: '+r.gate_accepted+'. Hidden outcome was not sent to Muse.';$('truth').hidden=!$('truth').hidden;};
$('download').onclick=()=>{if(!latest)return;const blob=new Blob([JSON.stringify(latest,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='stateproof_evidence_'+Date.now()+'.json';a.click();URL.revokeObjectURL(url);};
load();
</script></body></html>'''


class StudioState:
    def __init__(self, *, live_enabled: bool = False, max_live: int = 3, evidence_dir: Path | None = None):
        self.live_enabled = live_enabled
        self.remaining_live_calls = max_live
        self.csrf = secrets.token_urlsafe(32)
        self.lock = Lock()
        self.run_lock = Lock()
        self.evidence_dir = evidence_dir


def make_handler(state: StudioState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "StateProofStudio/0.1"

        def _send(self, code: int, value: bytes, mime: str):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'")
            self.send_header("Content-Length", str(len(value)))
            self.end_headers()
            self.wfile.write(value)

        def _json(self, code: int, payload: dict):
            self._send(code, json.dumps(payload, sort_keys=True).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            # Browsers may append benign tracking query strings to local URLs.
            # Route on the parsed path, not the entire path+query string.
            request_path = urlparse(self.path).path
            if request_path in ("/", "/index.html"):
                self._send(200, _HTML.replace("__CSRF__", escape(state.csrf, quote=True)).encode(), "text/html; charset=utf-8")
            elif request_path == "/api/cases":
                self._json(200, {"cases": public_cases(), "live_enabled": state.live_enabled,
                                 "remaining_live_calls": state.remaining_live_calls})
            else:
                self._json(404, {"error": "Not found"})

        def do_POST(self):
            request_path = urlparse(self.path).path
            if request_path not in ("/api/run", "/api/gate-challenge"):
                self._json(404, {"error": "Not found"})
                return
            # Keep local-only API immune to cross-site form/fetch requests.
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if (self.headers.get("Origin") != expected_origin or
                    self.headers.get("X-CSRF-Token") != state.csrf or
                    self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json"):
                self._json(403, {"error": "Rejected request origin or token"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                size = 0
            if size <= 0 or size > 2048:
                self._json(400, {"error": "Invalid request size"})
                return
            try:
                payload = json.loads(self.rfile.read(size))
                if type(payload) is not dict:
                    raise ValueError("Invalid request fields")
                if request_path == "/api/gate-challenge":
                    if set(payload) != {"case_index"}:
                        raise ValueError("Invalid negative-control request fields")
                    index, mode = payload["case_index"], "negative_control"
                else:
                    if set(payload) != {"case_index", "mode"}:
                        raise ValueError("Invalid investigation request fields")
                    index, mode = payload["case_index"], payload["mode"]
                if type(index) is not int or index not in range(len(cohort())) or mode not in ("offline", "meta", "negative_control"):
                    raise ValueError("Invalid case or mode")
            except (ValueError, TypeError):
                self._json(400, {"error": "Invalid JSON request"})
                return
            if not state.run_lock.acquire(blocking=False):
                self._json(429, {"error": "Another investigation is in progress"})
                return
            try:
                if mode == "meta":
                    with state.lock:
                        if not state.live_enabled or state.remaining_live_calls < 1:
                            self._json(403, {"error": "Live Muse disabled or limit reached"})
                            return
                        # Charge the session allowance before attempting an API call. No automatic retry.
                        state.remaining_live_calls -= 1
                if mode == "negative_control":
                    result = {"control": run_negative_control(index)}
                else:
                    result = run_studio_case(index, mode)
                if state.evidence_dir:
                    state.evidence_dir.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                    prefix = "m26" if mode == "negative_control" else "m25"
                    name = f"{prefix}_{mode}_case{index}_{stamp}_{secrets.token_hex(3)}.json"
                    (state.evidence_dir / name).write_text(json.dumps(result, indent=2))
                result["remaining_live_calls"] = state.remaining_live_calls
                self._json(200, result)
            except Exception as exc:
                # Do not echo secrets, stack traces, or raw provider errors into the browser.
                self.log_error("Investigation error (%s)", type(exc).__name__)
                self._json(500, {"error": "Investigation failed. Check local terminal logs; no automatic retry was attempted."})
            finally:
                state.run_lock.release()

        def log_message(self, fmt, *args):
            # Avoid logging any request bodies or keys.
            return
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Local-only StateProof evidence investigation studio")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-live", type=int, default=3)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not 0 <= args.max_live <= 10:
        parser.error("Port must be 1024..65535 and max-live must be 0..10")
    enabled = os.environ.get("STATEPROOF_ENABLE_META") == "1" and args.max_live > 0
    if enabled and not os.environ.get("MODEL_API_KEY"):
        parser.error("MODEL_API_KEY must be exported before enabling Meta calls")
    evidence_dir = Path.cwd() / "evidence" / "pilots"  # excluded from repo by default
    state = StudioState(live_enabled=enabled, max_live=args.max_live if enabled else 0,
                        evidence_dir=evidence_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    print(f"StateProof Lab: http://127.0.0.1:{args.port}", flush=True)
    print("Live Meta:", "enabled" if enabled else "disabled", "· max calls:", state.remaining_live_calls, flush=True)
    print("Local synthetic workflows only. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
