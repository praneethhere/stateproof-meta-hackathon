"""Sealed, small-sample contract-to-crash pilot evaluation.

Use independently authored challenge contracts. FREEZE before asking the model to
plan. The PRIVATE simulator is never sent to Muse; only public API docs are.

This is a tiny diagnostic comparison, not a benchmark of general superiority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .crashlab import (
    baseline_plan, canonical, digest, execute_synthetic_crash,
    load_contract, muse_plan, validate_plan,
)

SCHEMA = "crashlab-heldout-pilot-v1"
STRATEGIES = ("writes_first", "keyword", "random", "muse")
MAX_CASES = 4


def _sha_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _load_freeze(freeze_path: Path) -> dict:
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("schema") != SCHEMA:
        raise ValueError("Unsupported evaluation protocol")
    if freeze.get("protocol") != {
        "fault_phase": "after_commit_lost_ack",
        "budget_plans_per_case": 1,
        "random_seed": 2026,
        "primary_metric": "cases_with_oracle_confirmed_false_success",
        "actor": "deterministic_bounded_retry_client",
    }:
        raise ValueError("Evaluation protocol differs from frozen v1")
    cases = freeze.get("cases")
    if not isinstance(cases, list) or not 2 <= len(cases) <= MAX_CASES:
        raise ValueError("Expected two to four independently-authored contracts")
    if len({x.get("name") for x in cases}) != len(cases):
        raise ValueError("Duplicate case names")
    for entry in cases:
        if not isinstance(entry, dict) or set(entry) != {"name", "path", "contract_sha256", "public_sha256"}:
            raise ValueError("Invalid frozen case")
        if not isinstance(entry["name"], str) or not entry["name"].replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid case name")
        for key in ("contract_sha256", "public_sha256"):
            if not isinstance(entry[key], str) or len(entry[key]) != 64:
                raise ValueError("Invalid digest")
    return freeze


def freeze_cases(paths: list[str | Path], destination: str | Path) -> dict:
    """Make one immutable-by-convention manifest before running live evaluations."""
    if not 2 <= len(paths) <= MAX_CASES:
        raise ValueError("Supply 2-4 contracts")
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f"Already frozen: {destination}")
    entries = []
    for p in paths:
        path = Path(p).resolve()
        data = load_contract(path)
        entries.append({
            "name": path.stem,
            "path": str(path),
            "contract_sha256": _sha_file(path),
            "public_sha256": digest(data["public"]),
        })
    if len({x["name"] for x in entries}) != len(entries):
        raise ValueError("Use uniquely named contracts")
    freeze = {
        "schema": SCHEMA,
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "cases": entries,
        "protocol": {
            "fault_phase": "after_commit_lost_ack",
            "budget_plans_per_case": 1,
            "random_seed": 2026,
            "primary_metric": "cases_with_oracle_confirmed_false_success",
            "actor": "deterministic_bounded_retry_client",
        },
        "scope": "Two to four synthetic workflows; exploratory, not a statistically representative benchmark.",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    return freeze


def evaluate(freeze_path: str | Path, *, live: bool = False,
             client: Any = None, effort: str = "high") -> dict:
    freeze_path = Path(freeze_path).resolve()
    freeze = _load_freeze(freeze_path)
    rows = []
    for entry in freeze["cases"]:
        path = Path(entry["path"])
        if not path.is_file() or _sha_file(path) != entry["contract_sha256"]:
            raise ValueError(f"Contract changed after freezing: {entry['name']}")
        data = load_contract(path)
        if digest(data["public"]) != entry["public_sha256"]:
            raise ValueError("Public contract changed after freeze")
        for strategy in STRATEGIES if live else STRATEGIES[:-1]:
            if strategy == "muse":
                plan, usage = muse_plan(data, client=client, effort=effort)
            else:
                plan = baseline_plan(data, strategy, seed=freeze["protocol"]["random_seed"])
                usage = {"input_tokens": 0, "output_tokens": 0}
            plan = validate_plan(plan, data)
            # Enforce the already frozen equal-phase protocol. Do NOT silently
            # rewrite a model-proposed phase, or execute a different fault and
            # compare that result to baselines with the fixed phase.
            prescribed_phase = freeze["protocol"]["fault_phase"]
            protocol_compliant = plan["phase"] == prescribed_phase
            if not protocol_compliant and strategy != "muse":
                raise AssertionError("Frozen baseline implementation violates the fault-phase protocol")
            result = execute_synthetic_crash(data, plan) if protocol_compliant else None
            rows.append({
                "case": entry["name"],
                "strategy": strategy,
                "operation_id": plan["operation_id"],
                "phase": plan["phase"],
                "hypothesis": plan["hypothesis"],
                "readback_proposal": plan["readback"],
                "protocol_compliant": protocol_compliant,
                "invalid_reason": None if protocol_compliant else "MODEL_SELECTED_NONFROZEN_FAULT_PHASE",
                "oracle_confirmed_false_success": result["false_success"] if result else False,
                "observed_effect_count": result["oracle"]["effect_count"] if result else None,
                "expected_effect_count": result["oracle"]["expected_count"] if result else 1,
                "severity_weight_if_exposed": result["oracle"]["severity"] if result and result["false_success"] else 0,
                "usage": usage,
            })
    summary = {}
    for strategy in STRATEGIES if live else STRATEGIES[:-1]:
        subset = [r for r in rows if r["strategy"] == strategy]
        summary[strategy] = {
            "confirmed_exposures": sum(bool(r["oracle_confirmed_false_success"]) for r in subset),
            "invalid_phase_selections": sum(not r["protocol_compliant"] for r in subset),
            "evaluated_cases": len(subset),
            "severity_weight_sum": sum(r["severity_weight_if_exposed"] for r in subset),
            "input_tokens": sum(r["usage"]["input_tokens"] for r in subset),
            "output_tokens": sum(r["usage"]["output_tokens"] for r in subset),
        }
    return {
        "schema": SCHEMA,
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "live_muse" if live else "offline_baselines_only",
        "freeze_sha256": _sha_file(freeze_path),
        "protocol": freeze["protocol"],
        "summary": summary,
        "rows": rows,
        "interpretation_limit": (
            "Exploratory, synthetic and only 2-4 contracts. No significance, general superiority, "
            "real-system reliability, or model-generated remediation claim is supported. "
            "The test actor is deterministic; Muse only chooses the crash plan. "
            "An out-of-protocol Muse phase counts as a miss and is not executed."
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Frozen, small-sample CrashLab comparison")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze", help="Freeze 2-4 independent synthetic contracts BEFORE model evaluation")
    f.add_argument("--contracts", nargs="+", required=True)
    f.add_argument("--out", required=True)
    e = sub.add_parser("run", help="Run equal-budget baseline comparisons; optionally Muse")
    e.add_argument("--freeze", required=True)
    e.add_argument("--live", action="store_true", help="Use real Muse API once for each frozen contract")
    e.add_argument("--accept-api-cost", action="store_true", help="Additional affirmative consent for API charges")
    e.add_argument("--effort", choices=("medium", "high", "max"), default="high")
    e.add_argument("--out", required=True)
    args = p.parse_args()
    if args.cmd == "freeze":
        obj = freeze_cases(args.contracts, args.out)
        print(json.dumps({"status": "FROZEN", "cases": [x["name"] for x in obj["cases"]],
                          "protocol_path": args.out, "note": "Do not edit challenge contracts after this point"}, indent=2))
    else:
        if args.live and not args.accept_api_cost:
            p.error("Live evaluation requires BOTH --live and --accept-api-cost")
        if args.accept_api_cost and not args.live:
            p.error("--accept-api-cost is only valid with --live")
        out = Path(args.out)
        if out.exists():
            p.error("Output already exists; do not silently overwrite recorded evidence")
        result = evaluate(args.freeze, live=args.live, effort=args.effort)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"mode": result["mode"], "summary": result["summary"],
                          "result_path": str(out)}, indent=2))


if __name__ == "__main__":
    main()
