"""M6: Read-only, source-validated showcase of actual local HTTP crash experiments.

This module never contacts Meta, opens sockets, or executes workflow operations.
It summarizes previously recorded M5 HTTP receipts into a self-contained static HTML.
The receipts are local evidence, NOT cryptographically attested execution traces.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from stateproof.crashlab import canonical, digest

ROLES = {
    "blind_retry": ("retry", False),
    "readback_first": ("readback", False),
    "guarded_retry": ("retry", True),
    "muse_actor": ("muse", False),
}
MAX_SIZE = 2_000_000


def _receipt(path: str | Path, role: str) -> dict:
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_SIZE:
        raise ValueError(f"Missing or oversized M5 receipt: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "stateproof-crashlab-http-m5-v1":
        raise ValueError("Unsupported or malformed M5 receipt")
    saved_hash = value.get("receipt_sha256")
    if saved_hash != digest({k: v for k, v in value.items() if k != "receipt_sha256"}):
        raise ValueError(f"Receipt changed since SHA-256 was recorded: {path.name}")
    actor, guarded = ROLES[role]
    if value.get("actor") != actor or value.get("guarded") is not guarded:
        raise ValueError(f"Wrong M5 experiment role: {role}")
    if value.get("execution") != "actual_loopback_http_file_sqlite" or value.get("synthetic") is not True:
        raise ValueError("This report accepts only isolated real-HTTP M5 episodes")
    if value.get("fault") != "after_commit_lost_ack":
        raise ValueError("M6 only compares identical after-commit lost-ack faults")
    oracle = value.get("private_oracle")
    report = value.get("actor_report")
    server_events = value.get("server_events")
    actor_events = value.get("actor_events")
    if not isinstance(oracle, dict) or not isinstance(report, dict):
        raise ValueError("Missing independent oracle or actor report")
    if not isinstance(server_events, list) or not isinstance(actor_events, list):
        raise ValueError("Missing M5 execution events")
    count, attempts = oracle.get("effect_count"), value.get("attempts")
    if type(count) is not int or count < 0 or type(attempts) is not int or attempts < 1:
        raise ValueError("Bad counts")
    if len(server_events) != attempts:
        raise ValueError("Recorded attempts disagree with HTTP server events")
    if sum(ev.get("committed") is True for ev in server_events if isinstance(ev, dict)) != count:
        raise ValueError("Commit events disagree with private SQLite oracle")
    if oracle.get("expected_count") != 1 or oracle.get("correct_state") is not (count == 1):
        raise ValueError("Oracle invariant inconsistent")
    false_done = report.get("status") == "DONE" and count != 1
    if value.get("false_done") is not false_done:
        raise ValueError("False-success claim inconsistent with the oracle")
    if not isinstance(value.get("operation_id"), str):
        raise ValueError("Missing operation ID")
    if role == "muse_actor" and value.get("model") != "muse-spark-1.3":
        raise ValueError("Missing verified model identity")
    return value


def build_public_record(paths: dict[str, str | Path]) -> dict:
    if set(paths) != set(ROLES):
        raise ValueError(f"Need exactly these four roles: {', '.join(ROLES)}")
    raw = {role: _receipt(paths[role], role) for role in ROLES}
    operations = {x["operation_id"] for x in raw.values()}
    contracts = {x.get("public_contract_sha256") for x in raw.values()}
    if len(operations) != 1 or len(contracts) != 1:
        raise ValueError("Receipts do not describe the same operation and public contract")
    result = {"schema": "stateproof-m6-live-http-showcase-v1",
              "scope": "Synthetic local HTTP with SQLite, not production",
              "operation": next(iter(operations)),
              "fault": "after_commit_lost_ack",
              "observations": {}}
    for role, rec in raw.items():
        model_usage = rec.get("model_usage", {})
        result["observations"][role] = {
            "actor": rec["actor"], "guarded": rec["guarded"],
            "agent_report": {"status": rec["actor_report"].get("status", "UNAVAILABLE"),
                             "reason": str(rec["actor_report"].get("reason", ""))[:500]},
            "effect_count": rec["private_oracle"]["effect_count"],
            "expected_count": 1,
            "false_done": rec["false_done"],
            "attempts": rec["attempts"],
            "server_events": [{"attempt": x.get("attempt"),
                               "phase": x.get("phase"),
                               "committed": bool(x.get("committed", False)),
                               "deduplicated": bool(x.get("deduplicated", False)),
                               "response_delivered": bool(x.get("response_delivered", False))}
                              for x in rec["server_events"]],
            "actor_events": [{"tool": str(x.get("tool", "unknown"))[:50],
                              "accepted": x.get("accepted"),
                              "observation": _public_observation(x.get("observation"))}
                             for x in rec["actor_events"]],
            "model_tokens": {"input": model_usage.get("input_tokens", 0),
                             "output": model_usage.get("output_tokens", 0)},
            "receipt_sha256": rec["receipt_sha256"]}
    result["record_sha256"] = digest(result)
    return result


def _public_observation(value: Any) -> dict:
    if not isinstance(value, dict):
        return {"status": "not recorded"}
    keys = ("ok", "error", "transport", "effect_count", "expected_count", "accepted", "recorded", "deduplicated")
    result = {}
    for key in keys:
        v = value.get(key)
        if type(v) in (str, int, bool) and len(str(v)) <= 120:
            result[key] = v
    return result


def render_html(public: dict) -> str:
    if public.get("schema") != "stateproof-m6-live-http-showcase-v1":
        raise ValueError("Not an M6 sanitized record")
    embedded = json.dumps(public, ensure_ascii=True, separators=(",", ":"))
    # Never allow JSON text to terminate the script, even if source reason was hostile.
    embedded = embedded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    # Appended from a literal static template; never evaluate user-provided code.
    return _HTML_TEMPLATE.replace("/*RECORD_JSON*/{}", embedded)


_HTML_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StateProof CrashLab · Real HTTP Recovery Experiment</title>
<style>
:root{color-scheme:dark;--bg:#080f1c;--surface:#111e31;--panel:#16263e;--line:#2b405d;--text:#f0f6ff;--muted:#adc3d9;--mint:#4ce5bf;--red:#ff7c8a;--gold:#ffd48c}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 95% 0,#20385f 0,transparent 50%),var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,Arial,sans-serif}main{max-width:1080px;padding:30px 22px 80px;margin:auto}.brand{font-size:13px;letter-spacing:.18em;font-weight:900}.brand span{color:var(--mint)}h1{font-size:clamp(38px,6vw,65px);line-height:1.06;letter-spacing:-.055em;margin:26px 0 15px}h1 em{font-style:normal;color:var(--mint)}.eyebrow{font-size:11px;letter-spacing:.19em;text-transform:uppercase;color:var(--muted);font-weight:800}.intro{max-width:780px;color:var(--muted);font-size:17px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0}.stat,.panel{background:var(--surface);border:1px solid var(--line);border-radius:15px;padding:20px}.stat strong{display:block;font-size:33px;letter-spacing:-.04em}.stat small{color:var(--muted)}.positive{color:var(--mint)}.negative{color:var(--red)}.layout{display:grid;grid-template-columns:1fr 1fr;gap:14px}.buttons{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}button{font:inherit;border-radius:8px;background:var(--panel);border:1px solid var(--line);padding:10px 13px;color:var(--text);cursor:pointer;text-align:left}button:hover{border-color:var(--mint)}button.active{background:#194c50;border-color:var(--mint);color:#dbfff6}button.primary{background:var(--mint);color:#06292d;border-color:var(--mint);font-weight:800}p{margin:8px 0}h2{font-size:20px;margin:0 0 13px}h3{font-size:15px;margin:18px 0 10px;color:var(--muted)}.figure{font-size:46px;font-weight:850;letter-spacing:-.04em}.caption,.note{font-size:13px;color:var(--muted)}.list{margin:0;padding-left:20px}.list li{margin-bottom:11px}.step{border:1px solid var(--line);border-radius:10px;padding:10px;margin:9px 0;opacity:.52}.step.current{border-color:var(--mint);background:#17333f;opacity:1}.step.done{opacity:1}.tag{display:inline-block;border:1px solid var(--line);padding:2px 7px;border-radius:5px;font-size:11px;margin-left:7px}.warn{color:var(--gold)}.stack{display:grid;grid-template-columns:1fr;gap:14px;margin-top:14px}code{color:#a6f2e1;overflow-wrap:anywhere}.muted{color:var(--muted)}.foot{border-top:1px solid var(--line);margin-top:28px;padding-top:20px;color:var(--muted);font-size:13px}@media(max-width:760px){.layout,.stats{grid-template-columns:1fr}main{padding:24px 15px 60px}}
</style></head><body><main>
<div class="brand">STATEPROOF <span>CRASHLAB</span><span class="tag">M6 · REAL LOCAL HTTP</span></div>
<div class="eyebrow" style="margin-top:28px">Meta Global AI Developer Hackathon · controlled reliability experiment</div>
<h1>The API said nothing.<br><em>What did the agent do?</em></h1>
<p class="intro">A local HTTP service commits a transaction, then drops its response. The agent has to recover under uncertainty. Compare the actual actions of Meta Muse Spark 1.3 with deterministic retry policies—and reveal the independent SQLite ledger.</p>
<div class="stats"><div class="stat"><small>Blind retry · unguarded</small><strong class="negative" id="badCount">—</strong><small>Committed effects / 1 expected</small></div><div class="stat"><small>Muse agent · unguarded</small><strong class="positive" id="museCount">—</strong><small>Committed effects / 1 expected</small></div><div class="stat"><small>Blind retry · idempotency guard</small><strong class="positive" id="guardCount">—</strong><small>Committed effects / 1 expected</small></div></div>
<section class="panel"><div class="eyebrow">01 / Choose an observed recovery</div><div class="buttons" id="tabs"></div><div class="layout"><section class="panel"><div class="eyebrow">Agent report</div><h2 id="roleName">—</h2><p id="reason" class="muted"></p><div id="truth" class="figure"></div><p id="truthLine"></p><p class="caption">Agent report and private verifier are distinct observations.</p></section><section class="panel"><div class="eyebrow">Independent state check</div><div id="oracleCount" class="figure"></div><p id="oracleStatus"></p><p class="caption">The verifier opened the file-backed SQLite database separately. A SHA-256 receipt provides local change detection, not remote attestation.</p></section></div></section>
<section class="panel" style="margin-top:14px"><div class="eyebrow">02 / Captured execution events — not a synthetic reenactment</div><h2>What crossed the commit boundary?</h2><p class="caption">Server commit records and agent tool calls are two distinct event sequences; the lists do not imply synchronized timestamps.</p><div class="layout"><div><h3>HTTP server events</h3><div id="serverSteps"></div></div><div><h3>Agent-visible tool decisions</h3><div id="agentSteps"></div></div></div><div class="buttons"><button class="primary" id="play">▶ Play HTTP sequence</button><button id="reset">↺ Reset</button><button id="export">↓ Export sanitized evidence</button></div></section>
<div class="stack"><section class="panel"><div class="eyebrow">03 / What this experiment establishes</div><p><strong>The blind-retry policy can create duplicate external effects after a lost acknowledgment.</strong> A separate readback or server-side request-key deduplication prevents the duplicate in this reference setup. In the observed Muse run, the model inspected the ledger and did not retry.</p><p class="warn"><strong>Limitations:</strong> This is a local synthetic HTTP service with one operation and a readily available ledger—not an arbitrary API, production transaction, robust concurrency test, general model benchmark, or novel exactly-once protocol. Muse received explicit outcome-verification guidance. Other models and faults were not evaluated here.</p></section></div>
<div class="foot">Derived from locally saved M5 receipts with validated change-detection hashes and checked commit-count consistency. The page contains no API keys, private contracts, real client information, or access to the Meta API. <span id="digest"></span></div>
</main><script>
const DATA=/*RECORD_JSON*/{};
const LABELS={blind_retry:'Blind retry · vulnerable',readback_first:'Readback-first · deterministic',guarded_retry:'Blind retry · guarded',muse_actor:'Muse Spark 1.3 · real agent'};
const ROLES=['blind_retry','readback_first','guarded_retry','muse_actor'];
let selected='muse_actor',current=-1;let pending=0;
const $=id=>document.getElementById(id);
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function render(){const d=DATA.observations[selected];$('tabs').replaceChildren(...ROLES.map(k=>{const b=el('button',k===selected?'active':'',LABELS[k]);b.addEventListener('click',()=>{selected=k;current=-1;window.clearTimeout(pending);render()});return b}));$('roleName').textContent=LABELS[selected];$('reason').textContent=d.agent_report.reason;$('truth').textContent=d.agent_report.status;$('truth').className='figure '+(d.false_done?'negative':'positive');$('truthLine').textContent=d.false_done?'FALSE SUCCESS: actor reported DONE but 2 effects committed':'Model/client report: '+d.agent_report.status;$('oracleCount').textContent=d.effect_count+' / '+d.expected_count;$('oracleCount').className='figure '+(d.effect_count===1?'positive':'negative');$('oracleStatus').textContent=d.effect_count===1?'Exactly one committed effect observed':'Duplicate effects independently observed';$('serverSteps').replaceChildren(...d.server_events.map((ev,i)=>el('div','step '+(i<=current?'done ':'')+(i===current?'current':''),`Attempt ${ev.attempt} · ${ev.phase} · committed=${ev.committed} · response_delivered=${ev.response_delivered}${ev.deduplicated?' · deduplicated':''}`)));$('agentSteps').replaceChildren(...d.actor_events.map((e,i)=>el('div','step done',`${i+1}. ${e.tool} → ${JSON.stringify(e.observation)}`)));$('badCount').textContent=DATA.observations.blind_retry.effect_count+'/1';$('museCount').textContent=DATA.observations.muse_actor.effect_count+'/1';$('guardCount').textContent=DATA.observations.guarded_retry.effect_count+'/1';$('digest').textContent='Sanitized record SHA-256: '+DATA.record_sha256;}
function tick(){const d=DATA.observations[selected];if(current>=d.server_events.length-1)return;current++;render();if(current<d.server_events.length-1)pending=window.setTimeout(tick,1000)}
$('play').addEventListener('click',()=>{window.clearTimeout(pending);current=-1;tick()});$('reset').addEventListener('click',()=>{window.clearTimeout(pending);current=-1;render()});$('export').addEventListener('click',()=>{const blob=new Blob([JSON.stringify(DATA,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='crashlab_real_http_sanitized.json';a.click();window.setTimeout(()=>URL.revokeObjectURL(url),500)});render();
</script></body></html>'''


def main() -> None:
    ap = argparse.ArgumentParser(description="M6: sanitize and visualize existing M5 real HTTP receipts")
    for role in ROLES:
        ap.add_argument("--" + role.replace("_", "-"), type=Path, required=True)
    ap.add_argument("--html", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    paths = {role: getattr(a, role) for role in ROLES}
    public = build_public_record(paths)
    a.html.parent.mkdir(parents=True, exist_ok=True)
    a.html.write_text(render_html(public), encoding="utf-8")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(public, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "VERIFIED", "html": str(a.html), "sha256": sha256(a.html.read_bytes()).hexdigest(),
                      "real_http_runs": 4, "model_called": False, "private_data_exported": False}, indent=2))


if __name__ == "__main__":
    main()
