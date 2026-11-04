"""Post-hoc synthetic contract-drift audit of a previously recorded Muse policy.

Not a new Muse call, an external API test, or a production idempotency proof.
The model's document interpretation is compared to actual HTTP/SQLite sandbox
behavior; an intentionally changed sandbox implementation creates contrasts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from stateproof.crashlab import digest, load_contract
from stateproof.crashlab_http import LoopbackService, deterministic_actor
from stateproof.crashlab_policy import validate_policy, _writes
from stateproof.crashlab_retry_guard import RetryAuthorizationBoundary

# Public, predeclared SYNTHETIC implementation changes. Never applied to a real API.
DRIFT = {"reserve_slot": "none", "charge_freight": "request_key"}
FAULTS = ("after_commit_lost_ack", "before_commit_timeout")


def validate_record(data: dict, record: dict) -> None:
    if record.get("evidence_type") != "LIVE_META_MODEL_API_RESULT":
        raise ValueError("A recorded live Meta policy receipt is required")
    if record.get("strategy") != "muse" or record.get("meta", {}).get("model") != "muse-spark-1.3":
        raise ValueError("Not the expected Muse strategy/model")
    if not str(record.get("meta", {}).get("response_id", "")).startswith("resp_"):
        raise ValueError("Missing Meta response ID")
    if record.get("public_contract_sha256") != digest(data["public"]):
        raise ValueError("Policy receipt was generated against a different public contract")
    checksum = record.get("receipt_sha256")
    if not isinstance(checksum, str) or checksum != digest({k: v for k, v in record.items() if k != "receipt_sha256"}):
        raise ValueError("Original policy receipt checksum mismatch")
    validate_policy(record["policy"], data)


def audit(data: dict, record: dict, *, drift: dict[str, str] | None = None) -> dict:
    """Probe synthetic HTTP behavior without using private configuration for the observation.

    Ground-truth private simulator labels remain available solely for constructing
    a *synthetic* service. The auditor determines observed deduplication from
    direct SQLite count after two same-key calls, never from the label itself.
    """
    validate_record(data, record)
    drift = dict(DRIFT if drift is None else drift)
    ids = {o["id"] for o in _writes(data)}
    if any(k not in ids or v not in ("request_key", "none") for k, v in drift.items()):
        raise ValueError("Unrecognized synthetic drift configuration")
    policy = {p["operation_id"]: p for p in record["policy"]["policies"]}
    operations = []
    trials = []
    for op in _writes(data):
        op_id = op["id"]
        original = data["private_simulator"][op_id]["dedupe"]
        actual = drift.get(op_id, original)
        model_action = policy[op_id]["action"]
        with LoopbackService(operation=op_id, dedupe=actual, guarded=False,
                             fault="no_fault", readback_fault="normal") as probe:
            response1 = probe.execute()
            response2 = probe.execute()
            observed = probe.oracle()["effect_count"]
            if not (response1.get("ok") and response2.get("ok")) or observed not in (1, 2):
                raise RuntimeError("Unexpected synthetic sandbox probe response")
        observed_dedup = observed == 1
        docs_claim_dedup = model_action == "retry_same_key"
        mismatch = docs_claim_dedup != observed_dedup
        # A two-call sandbox probe by itself is NOT a production guarantee.
        # Only a documented guarantee AND a matching local probe enables the
        # *synthetic* verified boundary. The boundary also checks its service.
        permit_sandbox_retry = docs_claim_dedup and observed_dedup
        if docs_claim_dedup and not observed_dedup:
            status = "CRITICAL_CONTRACT_MISMATCH"
        elif not docs_claim_dedup and observed_dedup:
            status = "CONSERVATIVE_CONTRACT_MISMATCH"
        else:
            status = "MATCH"
        operations.append({
            "operation_id": op_id,
            "description": op["description"],
            "muse_policy": model_action,
            "muse_evidence_quote": policy[op_id]["quote"],
            "synthetic_implementation_altered": op_id in drift,
            "probe_first_ok": response1["ok"],
            "probe_second_deduplicated": response2.get("deduplicated"),
            "probe_independent_sqlite_effects": observed,
            "observed_request_key_deduplication": observed_dedup,
            "status": status,
            "synthetic_retry_authorized": permit_sandbox_retry,
        })
        for fault in FAULTS:
            with LoopbackService(operation=op_id, dedupe=actual, guarded=False,
                                 fault=fault, severity=1,
                                 readback_fault="stale_zero_once") as target:
                mode = "verified_idempotency" if permit_sandbox_retry else "hard_stop"
                boundary = RetryAuthorizationBoundary(target, mode=mode)
                report, events, _ = deterministic_actor(boundary, "readback")
                oracle = target.oracle()
                trials.append({
                    "operation_id": op_id, "fault": fault,
                    "model_policy": model_action,
                    "audited_boundary_mode": mode,
                    "agent": "deterministic_readback_first_not_muse",
                    "actor_report": report,
                    "actor_events": events,
                    "oracle_effects": oracle["effect_count"],
                    "correct_final_state": oracle["correct_state"],
                    "external_write_attempts": target.attempts,
                    "denied_writes": sum(x["decision"] == "DENY" for x in boundary.boundary_events),
                })
    report = {
        "schema": "stateproof-crashlab-contract-audit-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_type": "RECORDED_MUSE_POLICY_PLUS_DETERMINISTIC_SYNTHETIC_DRIFT_AUDIT",
        "model_policy_response_id": record["meta"]["response_id"],
        "model_policy_receipt_sha256": record["receipt_sha256"],
        "public_contract_sha256": digest(data["public"]),
        "drift_injected": drift,
        "probe": "two_same_request_key_calls_to_real_local_http_plus_direct_sqlite_count",
        "score": {
            "operations": len(operations),
            "critical_mismatches": sum(x["status"] == "CRITICAL_CONTRACT_MISMATCH" for x in operations),
            "conservative_mismatches": sum(x["status"] == "CONSERVATIVE_CONTRACT_MISMATCH" for x in operations),
            "correct_final_state": sum(x["correct_final_state"] for x in trials),
            "scenarios": len(trials),
            "duplicates_after_boundary": sum(x["oracle_effects"] > 1 for x in trials),
            "incomplete": sum(not x["correct_final_state"] for x in trials),
        },
        "operations": operations,
        "trials": trials,
        "limitations": [
            "POST-HOC hand-authored drift injection, not provider misconduct or a naturally observed contract change.",
            "Recorded Muse policy was generated against original descriptions; there were NO NEW model calls.",
            "All HTTP writes occur solely on disposable 127.0.0.1 SQLite synthetic services.",
            "A two-call probe cannot establish production idempotency across time, concurrency or failures.",
            "A deterministic actor, not Muse, executes the guarded recovery scenarios.",
            "The policy may be imperfect: safety here depends on an enforcing, fail-closed boundary.",
        ],
    }
    report["receipt_sha256"] = digest(report)
    return report


def sanitize_live_guard(record: dict) -> dict:
    """Validate and publish a minimal, synthetic, *separate* live Muse episode.

    This is not the original M7 run, and it is not a continuation of the M8B
    counterfactual. No secret headers, model prompts, call IDs or server internals.
    """
    if not isinstance(record, dict) or record.get("schema") != "stateproof-crashlab-m8-retry-boundary-v1":
        raise ValueError("Expected a real M8 retry-guard receipt")
    if record.get("receipt_sha256") != digest({k: v for k, v in record.items() if k != "receipt_sha256"}):
        raise ValueError("M8 receipt checksum mismatch")
    checks = (
        record.get("actor") == "muse",
        record.get("mode") == "hard_stop",
        record.get("fault") == "after_commit_lost_ack",
        record.get("readback_fault") == "stale_zero_once",
        record.get("guarded_server") is False,
        record.get("oracle", {}).get("effect_count") == 1,
        record.get("oracle", {}).get("correct_state") is True,
        record.get("actor_report", {}).get("status") == "DONE",
        record.get("denied_writes") == 1,
        record.get("external_write_attempts") == 1,
        record.get("actor_requested_writes") == 2,
    )
    if not all(checks):
        raise ValueError("Guard episode does not match expected synthetic live follow-up")
    allowed = {"effect_count", "expected_count", "intent_id", "error", "reason", "status", "ok", "recorded", "transport"}
    cleaned = []
    for step in record.get("actor_events", []):
        if not isinstance(step, dict) or step.get("tool") not in {"perform_operation", "inspect_ledger", "report_outcome"}:
            raise ValueError("Unexpected agent tool event")
        observation = step.get("observation", {})
        cleaned.append({"turn": step.get("turn"), "tool": step["tool"],
                        "observation": {k: observation[k] for k in allowed if k in observation}})
    if not cleaned or len(cleaned) > 12:
        raise ValueError("Unexpected event count")
    return {"evidence_type": "SEPARATE_SAVED_LIVE_MUSE_EPISODE_NOT_M7_CONTINUATION",
            "receipt_sha256": record["receipt_sha256"],
            "recorded_utc": record.get("recorded_utc"),
            "model_usage": record["model_usage"],
            "actor_report": record["actor_report"],
            "oracle_effect_count": record["oracle"]["effect_count"],
            "external_write_attempts": record["external_write_attempts"],
            "actor_requested_writes": record["actor_requested_writes"],
            "denied_writes": record["denied_writes"],
            "agent_events": cleaned}


def render_html(report: dict) -> str:
    def e(x: Any) -> str: return html.escape(str(x), quote=True)
    operations = report["operations"]
    critical = next((x for x in operations if x["status"] == "CRITICAL_CONTRACT_MISMATCH"), None)
    if critical is None:
        raise ValueError("Expected one synthetic critical drift for this viewer")
    trial = next(x for x in report["trials"] if x["operation_id"] == critical["operation_id"]
                 and x["fault"] == "after_commit_lost_ack")
    rows = "".join(
        '<tr><td><code>{}</code></td><td>{}</td><td>{}</td><td><strong class="{}">{}</strong></td><td>{}</td></tr>'.format(
            e(x["operation_id"]), e(x["muse_policy"]), x["probe_independent_sqlite_effects"],
            "danger" if x["status"] == "CRITICAL_CONTRACT_MISMATCH" else "muted",
            e(x["status"].replace("_", " ")), "DENY" if not x["synthetic_retry_authorized"] else "ALLOW (sandbox)")
        for x in operations)
    live = report.get("separate_live_guard_episode")
    live_panel = ""
    if live:
        timeline = "".join(
            '<li><code>{}</code><span>{}</span></li>'.format(e(v["tool"]),
                e(json.dumps(v["observation"], ensure_ascii=False)))
            for v in live["agent_events"])
        live_panel = f'''<section class="panel" id="muse-continuation"><div class="eyebrow">Separate recorded Muse execution · NOT counterfactual</div>
        <h2>Muse continued after the boundary refused the second write</h2>
        <div class="stats"><div class="stat"><strong>{e(live['actor_requested_writes'])}</strong><span>Agent requested writes</span></div>
        <div class="stat"><strong>{e(live['denied_writes'])}</strong><span>Denied write</span></div>
        <div class="stat"><strong>{e(live['oracle_effect_count'])}</strong><span>Final SQLite effect</span></div></div>
        <p>In a separately recorded live Muse Spark run under a lost acknowledgment and stale read, the tool boundary denied a second write. Muse then finished with <b>{e(live['actor_report']['status'])}</b>; the independent oracle observed one effect. One run, not a reliability estimate. This does not change the earlier M7 recorded failure or M8B replay.</p>
        <ol class="timeline">{timeline}</ol>
        <p class="mono">Saved receipt SHA-256: {e(live['receipt_sha256'])}</p></section>'''
    h = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="A recorded Muse contract policy meets an independently verified synthetic API drift fault">
<title>StateProof CrashLab | Contract Drift Audit</title>
<style>
:root{{--bg:#090f19;--panel:#151f30;--line:#304058;--text:#eef4ff;--mute:#aabdd5;--accent:#7eebda;--warn:#ff9d85}}
*{{box-sizing:border-box}}body{{background:radial-gradient(circle at 20% 0%,#1a354b 0%,var(--bg) 45%);color:var(--text);font:16px/1.55 system-ui,-apple-system,sans-serif;max-width:1150px;margin:0 auto;padding:28px}}
a{{color:var(--accent)}}h1{{font-size:clamp(2rem,5vw,3.7rem);line-height:1.1;margin:12px 0}}h2{{font-size:1.4rem}}p,small{{color:var(--mute)}}.eyebrow{{font-size:.75rem;font-weight:800;text-transform:uppercase;letter-spacing:.14em;color:var(--accent)}}
.panel{{border:1px solid var(--line);background:var(--panel);border-radius:18px;padding:22px;margin:20px 0}}.hero{{padding:14px 0 20px}}.stats{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}.stat strong{{display:block;font-size:2rem;color:var(--text)}}.stat span{{color:var(--mute);font-size:.85rem}}
.danger{{color:var(--warn)}}.muted{{color:var(--mute)}}.flow{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}.flow>div{{padding:20px;border:1px solid var(--line);background:var(--panel);border-radius:15px}}.flow h3{{margin:4px 0 8px}}.flow code{{word-break:break-word}}.tag{{display:inline-block;padding:5px 10px;border:1px solid var(--line);border-radius:999px;font-size:.75rem;margin:5px 4px 5px 0}}
.tablewrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:.82rem}}th,td{{padding:13px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}th{{color:var(--mute);text-transform:uppercase;font-size:.7rem}}.steps{{display:flex;gap:8px;margin:15px 0}}button{{border:1px solid var(--line);background:#26384c;color:var(--text);padding:10px 16px;border-radius:8px;cursor:pointer}}button[aria-pressed=true]{{background:#246d64;border-color:var(--accent)}}.step{{display:none;padding:22px;border:1px solid var(--line);background:#111d2b;border-radius:12px;min-height:112px}}.step.active{{display:block}}.mono{{font-family:ui-monospace,SFMono-Regular,monospace;font-size:.85rem}}.timeline{{list-style:decimal;padding-left:25px}}.timeline li{{border-bottom:1px solid var(--line);padding:10px;display:flex;gap:18px;align-items:start;flex-wrap:wrap}}.timeline li span{{font:12px/1.5 ui-monospace,monospace;color:var(--mute);overflow-wrap:anywhere}}blockquote{{margin:0;border-left:3px solid var(--accent);padding-left:18px}}footer{{padding:24px 0;color:var(--mute);font-size:.85rem}}
@media(max-width:750px){{.stats,.flow{{grid-template-columns:1fr}}body{{padding:18px}}.steps{{flex-wrap:wrap}}}}
</style></head><body>
<nav><a href="./index.html">Crash planner</a> · <a href="./recovery.html">Recovery lab</a> · <a href="./policy.html">Muse policy</a> · Contract audit</nav>
<header class="hero"><div class="eyebrow">StateProof CrashLab / Independent Contract Audit</div><h1>What if the API contract <span class="danger">lies?</span></h1>
<p>A real recorded <b>Muse Spark 1.3</b> policy meets a deliberately changed <b>synthetic</b> service. A local HTTP probe checks what actually commits; the retry boundary refuses an unsupported reissue.</p>
<div><span class="tag">RECORDED MUSE POLICY</span><span class="tag">DETERMINISTIC SYNTHETIC DRIFT</span><span class="tag">REAL LOOPBACK HTTP + SQLITE</span></div></header>
<section class="stats"><div class="stat panel"><strong>{report['score']['critical_mismatches']}</strong><span>Unsafe document/runtime disagreement</span></div><div class="stat panel"><strong>{report['score']['duplicates_after_boundary']}</strong><span>Duplicate effects after the boundary</span></div><div class="stat panel"><strong>{report['score']['correct_final_state']}/{report['score']['scenarios']}</strong><span>Correct final states (synthetic)</span></div></section>
{live_panel}
<h2>The causal chain</h2><div class="flow">
<div><div class="eyebrow">1 · Document interpretation</div><h3>Muse says retry</h3><p>From the original API description:</p><blockquote>{e(critical['muse_evidence_quote'])}</blockquote><p><span class="tag">{e(critical['muse_policy'])}</span></p></div>
<div><div class="eyebrow">2 · Independent sandbox probe</div><h3 class="danger">Actual result: 2 commits</h3><p>Two same-key HTTP writes to a deliberately changed local implementation produce <b>{critical['probe_independent_sqlite_effects']} SQLite effects</b>.</p><p>Documentation and observed sandbox behavior disagree.</p></div>
<div><div class="eyebrow">3 · Enforced boundary</div><h3>Retry denied</h3><p>In a separate lost-reply + stale-read scenario, the boundary permits only the first write.</p><p><b>{trial['oracle_effects']} effect</b>; {trial['denied_writes']} denied write(s). Safety is not proof of completion under every fault.</p></div>
</div>
<section class="panel"><h2>Step through the fault</h2><div class="steps" role="group" aria-label="Audit walkthrough">
<button data-index="0" aria-pressed="true">1 · Claim</button><button data-index="1" aria-pressed="false">2 · Probe</button><button data-index="2" aria-pressed="false">3 · Guard</button></div>
<div class="step active" data-step="0"><h3>Recorded Muse policy</h3><p class="mono">{e(critical['operation_id'])} → retry_same_key</p><p>Meta response: <code>{e(report['model_policy_response_id'])}</code>. This policy was recorded earlier; no model call occurred in this audit.</p></div>
<div class="step" data-step="1"><h3>Real local HTTP + SQLite probe</h3><p>POST same key → accepted; POST same key → accepted again; direct SQLite count = <b class="danger">2</b>. This synthetic implementation was intentionally changed; no real provider was tested.</p></div>
<div class="step" data-step="2"><h3>Denied unsafe retry under a lost reply</h3><p>Model advice is not authority. The observed probe contradicts the contract; the deterministic guard blocks the retry and reports the completion trade-off separately.</p></div>
</section>
<section class="panel"><h2>Every operation, not only the striking example</h2><p>Two synthetic implementation changes were specified before running this audit; other operations are unchanged.</p><div class="tablewrap"><table><thead><tr><th>Operation</th><th>Muse policy</th><th>Probe effects</th><th>Audit</th><th>Boundary</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="panel"><h2>What this proves—and what it doesn't</h2><p><b>Demonstrated:</b> This local harness detects mismatches between a model-extracted contract claim and an independently probed implementation, and can refuse an unsafe retry. The simulator deliberately introduced the mismatch.</p><p><b>Not demonstrated:</b> Real-world provider drift, universally reliable idempotency, a statistically powered Muse benchmark, or a new research method. A two-call probe does not establish production guarantees. The guarded actor here is deterministic, not a new Muse continuation.</p><a href="./audit-evidence.json">Inspect sanitized audit JSON</a> · <a href="https://github.com/praneethhere/stateproof-meta-hackathon">Public source</a></section>
<footer>Original Muse response {e(report['model_policy_response_id'])} · audit SHA-256 {e(report['receipt_sha256'])}</footer>
<script>for (const btn of document.querySelectorAll('button[data-index]')) {{ btn.addEventListener('click',()=>{{ const n=btn.dataset.index; for(const x of document.querySelectorAll('button[data-index]')) x.setAttribute('aria-pressed',String(x.dataset.index===n));for(const s of document.querySelectorAll('.step')) s.classList.toggle('active',s.dataset.step===n); }}); }}</script>
</body></html>'''
    return h


def main() -> None:
    p = argparse.ArgumentParser(description="CrashLab post-hoc synthetic API contract drift audit")
    p.add_argument("--contract", type=Path, default=Path("contracts/policy_challenges.json"))
    p.add_argument("--policy-evidence", type=Path, default=Path("docs/policy-evidence.json"))
    p.add_argument("--out", type=Path, default=Path("evidence/contract_audit_original.json"))
    p.add_argument("--public-out", type=Path, default=Path("docs/audit-evidence.json"))
    p.add_argument("--html", type=Path, default=Path("docs/audit.html"))
    p.add_argument("--live-guard-receipt", type=Path, help="Optional saved real Muse M8 guard episode (no new API call)")
    args = p.parse_args()
    paths = [args.out, args.public_out, args.html]
    if len(set(paths)) != len(paths) or any(x.exists() for x in paths):
        p.error("Output paths must be distinct and must not already exist")
    data = load_contract(args.contract)
    record = json.loads(args.policy_evidence.read_text(encoding="utf8"))
    result = audit(data, record)
    if args.live_guard_receipt:
        saved = json.loads(args.live_guard_receipt.read_text(encoding="utf8"))
        result["separate_live_guard_episode"] = sanitize_live_guard(saved)
        result["receipt_sha256"] = digest({k:v for k,v in result.items() if k != "receipt_sha256"})
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    for path, content in ((args.out, payload), (args.public_out, payload),
                          (args.html, render_html(result))):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf8")
    print(json.dumps({"evidence_type": result["evidence_type"],
                      "model_policy_response_id": result["model_policy_response_id"],
                      "score": result["score"],
                      "receipt_sha256": result["receipt_sha256"]}, indent=2))

if __name__ == "__main__":
    main()
