"""Create a self-contained, read-only CrashLab evaluation showcase.

It consumes one existing frozen M3 evaluation receipt and independently REPLAYS
synthetic SQLite fault episodes from the frozen contracts. It never invokes Meta,
changes the frozen inputs, or exports private simulator settings.

Replay events are freshly re-executed and are clearly distinguished from the
original model-planning observations in the HTML report.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import html
import json
from pathlib import Path
from typing import Any

from .crashlab import digest, execute_synthetic_crash, load_contract, validate_plan
from .crashlab_eval import _load_freeze, _sha_file, STRATEGIES, SCHEMA

LIMIT_BYTES = 2_000_000
SHOWCASE_SCHEMA = "stateproof-crashlab-showcase-v1"


def _read_small_json(path: Path) -> dict:
    if path.stat().st_size > LIMIT_BYTES:
        raise ValueError("Evaluation receipt is too large")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("Expected a JSON object")
    return obj


def _plan_from_row(row: dict) -> dict:
    return {"operation_id": row["operation_id"], "phase": row["phase"],
            "hypothesis": row["hypothesis"], "readback": row["readback_proposal"]}


def _assert_summary(summary: dict, rows: list[dict]) -> None:
    expected = {r["strategy"] for r in rows}
    if expected != set(summary):
        raise ValueError("Strategy summary/rows mismatch")
    for strategy in expected:
        subset = [r for r in rows if r["strategy"] == strategy]
        recorded = summary[strategy]
        actual = (sum(bool(r["oracle_confirmed_false_success"]) for r in subset),
                  sum(int(r["severity_weight_if_exposed"]) for r in subset),
                  len(subset),
                  sum(not r["protocol_compliant"] for r in subset))
        expected_values = (recorded["confirmed_exposures"], recorded["severity_weight_sum"],
                           recorded["evaluated_cases"], recorded["invalid_phase_selections"])
        if actual != expected_values:
            raise ValueError("Recorded summary disagrees with rows")


def prepare_showcase(freeze_path: str | Path, receipt_path: str | Path) -> dict:
    """Recheck hashes and rerun every scored episode, export no private schemas."""
    freeze_path, receipt_path = Path(freeze_path).resolve(), Path(receipt_path).resolve()
    frozen = _load_freeze(freeze_path)
    receipt = _read_small_json(receipt_path)
    if receipt.get("schema") != SCHEMA or receipt.get("mode") != "live_muse":
        raise ValueError("Showcase needs original M3 live Muse evaluation")
    if receipt.get("freeze_sha256") != _sha_file(freeze_path):
        raise ValueError("Receipt frozen manifest digest mismatch")
    if receipt.get("protocol") != frozen["protocol"]:
        raise ValueError("Evaluation protocol mismatch")
    rows = receipt.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Missing evaluation rows")
    case_names = [entry["name"] for entry in frozen["cases"]]
    expected_pairs = {(case, strategy) for case in case_names for strategy in STRATEGIES}
    try:
        actual_pairs = [(r["case"], r["strategy"]) for r in rows]
        if len(rows) != len(expected_pairs) or len(set(actual_pairs)) != len(rows) or set(actual_pairs) != expected_pairs:
            raise ValueError("Expected exactly one row for every case and strategy")
        _assert_summary(receipt["summary"], rows)
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed recorded rows") from exc

    contracts = {}
    for entry in frozen["cases"]:
        path = Path(entry["path"])
        if not path.is_file() or _sha_file(path) != entry["contract_sha256"]:
            raise ValueError(f"Frozen contract changed: {entry['name']}")
        data = load_contract(path)
        if digest(data["public"]) != entry["public_sha256"]:
            raise ValueError(f"Public contract changed: {entry['name']}")
        contracts[entry["name"]] = data

    sanitized_rows = []
    for case in case_names:
        for strategy in STRATEGIES:
            r = next(r for r in rows if r["case"] == case and r["strategy"] == strategy)
            data = contracts[case]
            plan = validate_plan(_plan_from_row(r), data)
            if bool(r["protocol_compliant"]) != (plan["phase"] == frozen["protocol"]["fault_phase"]):
                raise ValueError("Protocol compliance inconsistency")
            if r["protocol_compliant"]:
                replay = execute_synthetic_crash(data, plan)
                if (replay["oracle"]["effect_count"] != r["observed_effect_count"] or
                    replay["oracle"]["expected_count"] != r["expected_effect_count"] or
                    replay["false_success"] != r["oracle_confirmed_false_success"] or
                    (replay["oracle"]["severity"] if replay["false_success"] else 0) != r["severity_weight_if_exposed"]):
                    raise ValueError(f"Replay disagrees with recorded oracle: {case}/{strategy}")
                events = [{"attempt": e["attempt"], "observation": e["observation"],
                           "committed": bool(e["committed"])} for e in replay["events"]]
                status = replay["reported_status"]
            else:
                if r["oracle_confirmed_false_success"] or r["observed_effect_count"] is not None:
                    raise ValueError("Invalid-phase episode incorrectly scored")
                events = []
                status = "NOT_EXECUTED"
            sanitized_rows.append({
                "case": case, "strategy": strategy,
                "operation": plan["operation_id"], "phase": plan["phase"],
                "hypothesis": plan["hypothesis"], "proposed_readback": plan["readback"],
                "protocol_compliant": bool(r["protocol_compliant"]),
                "false_success": bool(r["oracle_confirmed_false_success"]),
                "observed_effect_count": r["observed_effect_count"],
                "expected_effect_count": r["expected_effect_count"],
                "severity_weight_if_exposed": r["severity_weight_if_exposed"],
                "actor_status": status,
                "replayed_events": events,
            })
    return {
        "schema": SHOWCASE_SCHEMA, "title": "StateProof CrashLab · Frozen evaluation",
        "model": "Muse Spark 1.3", "cases": case_names,
        "case_titles": {case: contracts[case]["public"]["scenario"] for case in case_names},
        "strategies": list(STRATEGIES),
        "summary": {k: {"confirmed_exposures": v["confirmed_exposures"],
                        "evaluated_cases": v["evaluated_cases"],
                        "severity_weight_sum": v["severity_weight_sum"],
                        "invalid_phase_selections": v["invalid_phase_selections"]}
                    for k, v in receipt["summary"].items()},
        "rows": sanitized_rows,
        "integrity": {
            "freeze_sha256": receipt["freeze_sha256"],
            "receipt_sha256": _sha_file(receipt_path),
            "protocol": frozen["protocol"],
            "contracts_reverified": True,
            "replays_reverified": True,
        },
        "disclosure": (
            "Two independently authored synthetic cases; one crash plan per case; fixed after-commit "
            "lost-acknowledgment fault. Muse selected the operation, not the retries. The actor was "
            "a deterministic retrying client. Oracle results come from a private synthetic SQLite "
            "simulator. Timeline events shown here are NEW DETERMINISTIC REPLAYS of the frozen "
            "plans, not live-model execution traces. Proposed readbacks are suggestions, not "
            "separately executed inspection calls. No broad model-superiority or real-world claim."
        ),
    }


def _safe_js_json(value: Any) -> str:
    # Prevent closing a script tag with content originating in API descriptions.
    return (json.dumps(value, ensure_ascii=True, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>CrashLab — The state doesn't lie</title>
<style>
:root{color-scheme:dark;--bg:#070b14;--card:#111a2a;--card2:#15223a;--stroke:#273754;--muted:#a7b6d3;--white:#f1f5ff;--teal:#49e2bd;--red:#ff787f;--blue:#79acff;--yellow:#ffd077}
*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;background:radial-gradient(ellipse at 80% -12%,#1c3159 0,transparent 46%),var(--bg);color:var(--white)}
main{max-width:1220px;margin:auto;padding:32px 24px 70px}.top{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:34px}.wordmark{font-weight:900;letter-spacing:.09em;font-size:14px}.wordmark b{color:var(--teal)}.micro{font-size:11px;color:#c4cce1;text-transform:uppercase;letter-spacing:.17em}.pill{border:1px solid #45736c;color:var(--teal);border-radius:99px;padding:8px 12px;font-size:12px}
h1{font-size:clamp(40px,6.3vw,84px);letter-spacing:-.067em;line-height:1.035;margin:8px 0 17px;max-width:1000px}.grad{color:var(--teal)}.sub{max-width:780px;font-size:17px;line-height:1.65;color:var(--muted);margin-bottom:30px}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:26px 0 34px}.metric{background:linear-gradient(145deg,#14223c,#101a2c);border:1px solid var(--stroke);padding:23px 24px;border-radius:16px}.metric span{font-size:12px;color:var(--muted)}.metric strong{display:block;font-size:43px;letter-spacing:-.045em;margin:7px 0}.metric small{font-size:12px;color:#b6c1d8}.metric strong.good{color:var(--teal)}
.shell{border:1px solid var(--stroke);border-radius:22px;background:#0d1422;overflow:hidden;box-shadow:0 28px 80px #0005}.toolbar{padding:19px 24px;border-bottom:1px solid var(--stroke);display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}.toolbar h2{font-size:18px;margin:0}.selector{display:flex;flex-wrap:wrap;gap:8px}button{cursor:pointer;border:1px solid #344564;border-radius:10px;padding:10px 15px;background:#17223a;color:var(--white);font-weight:700;font-size:13px}button:hover,button:focus-visible{border-color:var(--teal);outline:none}button[aria-pressed=true]{background:#1e4a4a;border-color:var(--teal);color:#c6fff0}button.primary{background:var(--teal);border-color:var(--teal);color:#072426}button:disabled{opacity:.4;cursor:default}.content{padding:24px}.label{font-size:11px;text-transform:uppercase;letter-spacing:.16em;color:#aebfdd}.grid{display:grid;grid-template-columns:1.15fr .85fr;gap:16px;margin-bottom:16px}.panel{border:1px solid var(--stroke);background:var(--card);border-radius:14px;padding:23px}.panel h3{margin:9px 0 12px;font-size:24px;overflow-wrap:anywhere}.panel p{color:#cbd5e8;line-height:1.65;margin:7px 0 13px}.line{margin:14px 0;padding-top:13px;border-top:1px solid var(--stroke)}.kv{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-top:12px}.bigcount{font-size:49px;letter-spacing:-.05em;font-weight:900}.bad{color:var(--red)}.ok{color:var(--teal)}.muted{color:var(--muted)}.mono{font:12px ui-monospace,Consolas,monospace;overflow-wrap:anywhere}.replayline{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:18px 0}.step{min-height:116px;padding:14px;border:1px solid #2c3b5d;border-radius:12px;background:#0e1729;opacity:.43;transition:opacity .25s,transform .25s,border-color .25s}.step.done,.step.now{opacity:1}.step.now{transform:translateY(-4px);border-color:var(--teal);box-shadow:0 0 0 1px #2f9a87}.step em{display:block;font-style:normal;color:var(--muted);font-size:10px;margin-bottom:10px}.step strong{display:block;font-size:14px;line-height:1.35}.step .detail{font-size:11px;line-height:1.45;color:#b9cae6;margin-top:7px}.controls{display:flex;gap:8px;margin:14px 0;flex-wrap:wrap}.compare{width:100%;border-collapse:collapse;margin-top:14px}.compare th,.compare td{padding:14px 11px;border-bottom:1px solid var(--stroke);text-align:left;font-size:13px}.compare th{font-size:11px;letter-spacing:.11em;text-transform:uppercase;color:#b4c2d9}.compare button{background:transparent;border:0;padding:0;text-align:left;text-decoration:underline;text-underline-offset:4px}.note{border-left:3px solid var(--yellow);background:#27251e;padding:12px 16px;margin-top:20px;color:#f8ebbf;font-size:13px;line-height:1.6}.footer{margin:28px 0;color:#9aaed0;font-size:12px;line-height:1.7}.footer code{word-break:break-all} .badge{font-size:11px;border-radius:6px;padding:5px 8px;border:1px solid #395b62;color:#7ff2d5}.badge.fail{color:#ffb3b7;border-color:#794b59}
@media(max-width:750px){main{padding:20px 12px 45px}.top{align-items:flex-start}.metrics{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.replayline{grid-template-columns:1fr 1fr}.content{padding:12px}.panel{padding:18px}.bigcount{font-size:40px}.compare th,.compare td{font-size:11px;padding:10px 5px}h1{font-size:44px}}
@media(prefers-reduced-motion:reduce){.step{transition:none}}
</style></head><body><main>
<div class="top"><div class="wordmark">STATEPROOF <b>CRASHLAB</b></div><div class="pill">● REPRODUCIBLE · SYNTHETIC</div></div>
<div class="micro">Meta Global AI Developer Hackathon · Experimental demonstration</div>
<h1>The API timed out.<br><span class="grad">What actually committed?</span></h1>
<p class="sub">Muse Spark reads unfamiliar API contracts and selects where to inject an acknowledgment-loss fault. A deterministic simulator replays the scenario. An independent state check exposes duplicate effects—and records the evidence.</p>
<div class="metrics"><div class="metric"><span>Muse · confirmed exposures</span><strong class="good" id="metric-muse">—</strong><small>In the frozen synthetic challenges</small></div><div class="metric"><span>Strong keyword baseline</span><strong id="metric-keyword">—</strong><small>Same one-plan execution budget</small></div><div class="metric"><span>Severity-weighted exposures</span><strong id="metric-severity">—</strong><small>Synthetic weights, not financial loss</small></div></div>
<section class="shell"><div class="toolbar"><h2>01 / Crash replay</h2><div class="selector" id="cases" aria-label="Select challenge"></div></div><div class="content">
<div class="grid"><article class="panel"><div class="label" id="scenario">Planner decision</div><h3 id="operation">—</h3><div class="selector" id="strategies" aria-label="Select strategy"></div><p id="hypothesis">—</p><div class="line"><div class="label">Proposed readback · not executed as a tool call</div><p id="readback">—</p></div></article>
<article class="panel"><div class="label">Independent synthetic oracle</div><div class="kv"><div><span id="state" class="badge">—</span><div class="bigcount" id="effects">—</div><span class="muted">effects observed / 1 expected</span></div></div><div class="line"><div class="kv"><span class="muted">Actor reported</span><b id="actor">—</b></div><div class="kv"><span class="muted">Severity weight if exposed</span><b id="severity">—</b></div></div></article></div>
<article class="panel"><div class="kv"><div><div class="label">Deterministic crash replay</div><h3 style="font-size:20px">What happened at the commit boundary?</h3></div><span class="badge">RE-EXECUTED</span></div><div class="replayline" id="timeline" role="status" aria-live="polite"></div><div class="controls"><button id="play" class="primary">▶ Play replay</button><button id="reset">↺ Reset</button><button id="evidence">↓ Export sanitized JSON</button></div><p class="muted" style="font-size:12px">Timeline generated by rerunning the frozen synthetic SQLite scenario. This is NOT a captured trace of the original model API call.</p></article>
<article class="panel" style="margin-top:16px"><div class="label">Equal-budget comparison</div><table class="compare"><thead><tr><th>Strategy</th><th>Chosen operation</th><th>Effects</th><th>False success?</th></tr></thead><tbody id="comparison"></tbody></table></article>
<div class="note"><b>Important scientific limitation.</b> These are two deliberately constructed synthetic workflows, not production systems. The agent-under-test is a deterministic retry client; Muse only chooses the crash plan. Random uses one fixed seed. All conclusions are restricted to these two workflows.</div>
</div></section><div class="footer"><p id="disclosure"></p><p><b>Frozen protocol SHA-256:</b> <code id="freezehash"></code> · <b>Recorded receipt SHA-256:</b> <code id="receipthash"></code></p><p>Runs entirely offline. This report embeds only sanitized planning results and synthetic replay events—not simulator definitions, credentials, or contract files.</p></div>
</main><script>
const DATA = __EMBEDDED_DATA__;
const $=(id)=>document.getElementById(id);
const LABELS={muse:'Muse Spark 1.3',keyword:'Keyword',writes_first:'Writes-first',random:'Random (fixed seed)'};
let chosenCase=DATA.cases[0], chosenStrategy='muse', playing=false, stepIndex=0, playbackId=null;
const matching=()=>DATA.rows.find(r=>r.case===chosenCase&&r.strategy===chosenStrategy);
const t=(tag,cls,txt)=>{const x=document.createElement(tag);if(cls)x.className=cls;x.textContent=txt;return x};
function renderButtons(){
  for(const [target,values,selected,cb] of [['cases',DATA.cases,chosenCase,(v)=>{chosenCase=v}],['strategies',DATA.strategies,chosenStrategy,(v)=>{chosenStrategy=v}]]){
    const host=$(target);host.replaceChildren();for(const v of values){const b=t('button','',target==='cases'?DATA.case_titles[v]:LABELS[v]);b.type='button';b.setAttribute('aria-pressed',String(selected===v));b.addEventListener('click',()=>{cb(v);render()});host.append(b)}
  }
}
function timelineFrames(row){
  if(!row.protocol_compliant)return [{headline:'Out of protocol',detail:'Plan was not executed or scored'}];
  const ev=row.replayed_events;
  const frames=[{headline:'Select operation',detail:row.operation+' · fixed lost-ack fault'}];
  for(const e of ev)frames.push({headline:e.attempt===1?'First attempt':'Bounded retry',detail:(e.committed?'Committed':'No new commit')+' · '+e.observation.replaceAll('_',' ')});
  frames.push({headline:'Independent oracle',detail:row.observed_effect_count+' effects / '+row.expected_effect_count+' expected'});
  return frames;
}
function drawFrames(row){
  $('timeline').replaceChildren();const frames=timelineFrames(row);
  frames.forEach((f,i)=>{const c=t('div','step'+(i<stepIndex?' done':i===stepIndex?' now':''),'');c.append(t('em','',String(i+1).padStart(2,'0')),t('strong','',f.headline),t('div','detail',f.detail));$('timeline').append(c)});
}
function stop(){if(playbackId!==null)clearInterval(playbackId);playbackId=null;playing=false}
function render(){stop();stepIndex=0;renderButtons();const row=matching();
  $('scenario').textContent='PLANNER DECISION · '+DATA.case_titles[chosenCase]; $('operation').textContent=row.operation; $('hypothesis').textContent=row.hypothesis; $('readback').textContent=row.proposed_readback;
  $('state').textContent=!row.protocol_compliant?'INVALID PLAN':row.false_success?'FALSE SUCCESS EXPOSED':'NO FALSE SUCCESS';
  $('state').className='badge'+(row.false_success?' fail':'');
  $('effects').textContent=row.observed_effect_count===null?'—':row.observed_effect_count+' / '+row.expected_effect_count;
  $('effects').className='bigcount '+(row.false_success?'bad':'ok');$('actor').textContent=row.actor_status;
  $('severity').textContent=String(row.severity_weight_if_exposed);drawFrames(row);
  const body=$('comparison');body.replaceChildren();
  for(const r of DATA.rows.filter(x=>x.case===chosenCase)){
    const tr=document.createElement('tr');const c1=document.createElement('td');const b=t('button','',LABELS[r.strategy]);b.addEventListener('click',()=>{chosenStrategy=r.strategy;render()});c1.append(b);
    tr.append(c1,t('td','mono',r.operation),t('td','',r.observed_effect_count===null?'Not run':String(r.observed_effect_count)),t('td','',r.false_success?'YES':'No'));body.append(tr)
  }
}
$('play').addEventListener('click',()=>{stop();stepIndex=0;playing=true;drawFrames(matching());playbackId=setInterval(()=>{stepIndex++;if(stepIndex>=timelineFrames(matching()).length){stop();stepIndex=timelineFrames(matching()).length-1}drawFrames(matching())},650)});
$('reset').addEventListener('click',()=>{stop();stepIndex=0;drawFrames(matching())});
$('evidence').addEventListener('click',()=>{const data={schema:DATA.schema,case:chosenCase,strategy:chosenStrategy,row:matching(),integrity:DATA.integrity,disclosure:DATA.disclosure};const blob=new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='crashlab_'+chosenCase+'_'+chosenStrategy+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500)});
$('metric-muse').textContent=DATA.summary.muse.confirmed_exposures+'/'+DATA.summary.muse.evaluated_cases;
$('metric-keyword').textContent=DATA.summary.keyword.confirmed_exposures+'/'+DATA.summary.keyword.evaluated_cases;
$('metric-severity').textContent=DATA.summary.muse.severity_weight_sum+' vs '+DATA.summary.keyword.severity_weight_sum;
$('disclosure').textContent=DATA.disclosure;
$('freezehash').textContent=DATA.integrity.freeze_sha256;$('receipthash').textContent=DATA.integrity.receipt_sha256;render();
</script></body></html>'''


def render_showcase(data: dict) -> str:
    if data.get("schema") != SHOWCASE_SCHEMA:
        raise ValueError("Wrong showcase schema")
    return _HTML.replace("__EMBEDDED_DATA__", _safe_js_json(data))


def export_showcase(freeze_path: str | Path, receipt_path: str | Path,
                    output_path: str | Path) -> dict:
    target = Path(output_path)
    if target.suffix.lower() != ".html":
        raise ValueError("Output must be .html")
    if target.exists():
        raise FileExistsError(f"Will not overwrite existing report: {target}")
    data = prepare_showcase(freeze_path, receipt_path)
    page = render_showcase(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return {"html_file": str(target), "sha256": sha256(page.encode()).hexdigest(),
            "cases": data["cases"], "strategies": data["strategies"],
            "replay_verified": True, "external_api_calls": 0,
            "private_simulator_exported": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate read-only, self-contained CrashLab demo from frozen receipts")
    parser.add_argument("--freeze", required=True, help="Original immutable frozen manifest")
    parser.add_argument("--results", required=True, help="Recorded M3 live results JSON")
    parser.add_argument("--html", required=True, help="New HTML output path; no overwrites")
    args = parser.parse_args()
    print(json.dumps(export_showcase(args.freeze, args.results, args.html), indent=2))


if __name__ == "__main__":
    main()
