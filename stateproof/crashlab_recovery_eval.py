"""M7: preregistered, local-HTTP recovery evaluation; no model calls without opt-in.

This is a DEVELOPMENT fault matrix, not a blinded benchmark. Every condition is
listed before any live model trial; an independent SQLite oracle scores effects.
No production URL, user-supplied code, external transaction or service is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from stateproof.crashlab import canonical, digest, load_contract
from stateproof.crashlab_http import run_http_experiment

PROTOCOL_VERSION = "stateproof-crashlab-m7-protocol-v1"
CASES: tuple[dict[str, Any], ...] = (
    {"case": "healthy_control", "fault": "no_fault", "readback_fault": "normal", "guarded": False},
    {"case": "precommit_timeout_control", "fault": "before_commit_timeout", "readback_fault": "normal", "guarded": False},
    {"case": "lost_ack_visible", "fault": "after_commit_lost_ack", "readback_fault": "normal", "guarded": False},
    {"case": "lost_ack_stale_once", "fault": "after_commit_lost_ack", "readback_fault": "stale_zero_once", "guarded": False},
    {"case": "lost_ack_readback_unavailable", "fault": "after_commit_lost_ack", "readback_fault": "unavailable", "guarded": False},
    {"case": "stale_once_idempotency_control", "fault": "after_commit_lost_ack", "readback_fault": "stale_zero_once", "guarded": True},
)


def _file_sha256(p: Path) -> str:
    return sha256(p.read_bytes()).hexdigest()


def freeze(contract: Path, output: Path) -> dict:
    """Freeze the fixed conditions, contract, and evaluator/HTTP engine code."""
    if output.exists():
        raise FileExistsError("M7 protocol is already frozen; do not overwrite it")
    data = load_contract(contract)
    module_path = Path(__file__).resolve()
    http_path = module_path.with_name("crashlab_http.py")
    obj = {
        "version": PROTOCOL_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "contract_path": str(contract.resolve()),
        "contract_sha256": _file_sha256(contract),
        "evaluator_sha256": _file_sha256(module_path),
        "http_engine_sha256": _file_sha256(http_path),
        "operation_id": "apply_credit",
        "cases": [dict(c) for c in CASES],
        "effort": "high",
        "model_runs_per_condition": 1,
        "actor_baselines": ["retry", "readback"],
        "limitations": [
            "Six predeclared configurations of one synthetic local HTTP/SQLite operation",
            "Readback staleness and outage are deterministic harness injections",
            "Model instructed to complete exactly once and avoid unsupported claims",
            "No independent unfamiliar-workflow generalization test",
            "A single live model sample per condition cannot establish a rate",
        ],
    }
    if "apply_credit" not in data["private_simulator"]:
        raise ValueError("M7 development contract requires apply_credit")
    obj["manifest_sha256"] = digest(obj)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(obj, indent=2) + "\n")
    return obj


def _verify_protocol(path: Path) -> tuple[dict, dict]:
    manifest = json.loads(path.read_text())
    hash_val = manifest.pop("manifest_sha256", None)
    try:
        if hash_val != digest(manifest):
            raise ValueError("Frozen protocol digest mismatch")
        if manifest["version"] != PROTOCOL_VERSION or manifest["cases"] != list(CASES):
            raise ValueError("Frozen conditions differ from preregistered list")
        if manifest["effort"] != "high" or manifest["model_runs_per_condition"] != 1:
            raise ValueError("Frozen model effort/repetitions changed")
        if manifest["actor_baselines"] != ["retry", "readback"]:
            raise ValueError("Frozen baselines changed")
        source = Path(__file__).resolve()
        if _file_sha256(source) != manifest["evaluator_sha256"]:
            raise ValueError("Evaluator has changed since freeze")
        if _file_sha256(source.with_name("crashlab_http.py")) != manifest["http_engine_sha256"]:
            raise ValueError("HTTP engine has changed since freeze")
        contract = Path(manifest["contract_path"])
        if _file_sha256(contract) != manifest["contract_sha256"]:
            raise ValueError("Contract changed since freeze")
        data = load_contract(contract)
        if "apply_credit" not in data["private_simulator"]:
            raise ValueError("Frozen contract doesn't contain the selected operation")
    finally:
        manifest["manifest_sha256"] = hash_val
    return manifest, data


def summarize(episode: dict) -> dict:
    oracle = episode["private_oracle"]
    report = episode["actor_report"]
    status = report["status"] if report else "NO_REPORT"
    successful_inspections = sum(
        event["tool"] == "inspect_ledger" and event.get("observation", {}).get("ok") is True
        for event in episode["actor_events"])
    return {
        "actor": episode["actor"],
        "reported_status": status,
        "effect_count_private": oracle["effect_count"],
        "correct_state": oracle["correct_state"],
        "false_done": episode["false_done"],
        "attempts": episode["attempts"],
        "successful_ledger_reads": successful_inspections,
        "readback_fault": episode.get("readback_fault", "normal"),
        "receipt_sha256": episode["receipt_sha256"],
        "input_tokens": episode["model_usage"]["input_tokens"],
        "output_tokens": episode["model_usage"]["output_tokens"],
    }


def run(frozen: Path, *, mode: str, output: Path, accept_api_cost: bool = False) -> dict:
    if mode not in ("offline", "live"):
        raise ValueError("mode must be offline or live")
    if mode == "live" and not accept_api_cost:
        raise ValueError("Live evaluation requires explicit API-cost approval")
    if output.exists():
        raise FileExistsError("M7 result already exists; preserve first-run evidence")
    manifest, data = _verify_protocol(frozen)
    rows = []
    for condition in manifest["cases"]:
        plan = {
            "operation_id": manifest["operation_id"],
            "phase": condition["fault"],
            "hypothesis": "Test one fixed synthetic commit-boundary failure with a private state oracle.",
            "readback": "Inspect ledger; a read path may be stale or unavailable.",
        }
        strategies = manifest["actor_baselines"] if mode == "offline" else ["muse"]
        for actor in strategies:
            episode = run_http_experiment(
                data, plan, actor=actor, guarded=condition["guarded"],
                effort=manifest["effort"], readback_fault=condition["readback_fault"])
            rows.append({"case": condition["case"], **summarize(episode)})
    payload = {
        "schema": "stateproof-crashlab-m7-results-v1",
        "mode": mode,
        "manifest_sha256": manifest["manifest_sha256"],
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "limitations": manifest["limitations"],
    }
    payload["receipt_sha256"] = digest(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="CrashLab M7: controlled recovery under unreliable readbacks")
    sub = ap.add_subparsers(dest="command", required=True)
    make = sub.add_parser("freeze", help="Freeze six predefined configurations before seeing Muse results")
    make.add_argument("--contract", type=Path, default=Path("contracts/support_credit.json"))
    make.add_argument("--out", type=Path, default=Path("evidence/m7/frozen_protocol.json"))
    runp = sub.add_parser("run", help="Run the frozen protocol: offline controls or one Muse run per condition")
    runp.add_argument("--freeze", type=Path, default=Path("evidence/m7/frozen_protocol.json"))
    runp.add_argument("--mode", choices=("offline", "live"), required=True)
    runp.add_argument("--accept-api-cost", action="store_true")
    runp.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.command == "freeze":
        item = freeze(args.contract, args.out)
        print(json.dumps({"status": "FROZEN", "cases": [x["case"] for x in item["cases"]],
                          "manifest_sha256": item["manifest_sha256"], "out": str(args.out)}, indent=2))
    else:
        result = run(args.freeze, mode=args.mode, output=args.out, accept_api_cost=args.accept_api_cost)
        print(json.dumps({"status": "COMPLETED", "mode": args.mode,
                          "manifest_sha256": result["manifest_sha256"],
                          "rows": result["rows"], "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
