"""Export minimal, executable *synthetic* regression tests from CrashLab receipts.

Generated tests intentionally fail while the described reference simulator remains
vulnerable. These are reproductions, not claims about external production systems.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from .crashlab import load_contract, validate_plan, execute_synthetic_crash, canonical, digest

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def make_test_source(report: dict, contract: dict) -> str:
    """Produce a test of the *correctness invariant*, not a test that merely passes on failure."""
    if not isinstance(report, dict) or report.get("schema") != "stateproof-crashlab-v1":
        raise ValueError("Not a supported CrashLab receipt")
    if report.get("contract_sha256") != digest(contract["public"]):
        raise ValueError("Receipt belongs to a different contract")
    plan = validate_plan(report.get("plan"), contract)
    result = report.get("result", {})
    if result.get("actor") != "deterministic_bounded_retry_client":
        raise ValueError("Expected deterministic synthetic actor; do not relabel model behavior")
    if not result.get("false_success") or result.get("oracle", {}).get("correct_state") is not False:
        raise ValueError("Generate a failing regression only from a verified synthetic failure")
    expected = execute_synthetic_crash(contract, plan)
    if not expected["false_success"] or expected["oracle"] != result.get("oracle"):
        raise ValueError("Current contract no longer reproduces the recorded failure")

    # JSON data embedded as a quoted JSON literal; no supplied Python executes.
    public_json = canonical(contract["public"])
    private_json = canonical(contract["private_simulator"])
    plan_json = canonical(plan)
    return ('''"""GENERATED SYNTHETIC REGRESSION — expected to FAIL until reference adapter is fixed.

Does NOT exercise a real payment provider or a Muse agent under test.
Review and adapt this invariant to a real sandboxed API before production use.
"""\n'''
            + 'import json\n'
            + 'from stateproof.crashlab import execute_synthetic_crash\n\n'
            + f'PUBLIC = json.loads({public_json!r})\n'
            + f'PRIVATE = json.loads({private_json!r})\n'
            + f'PLAN = json.loads({plan_json!r})\n\n'
            + 'def test_retry_does_not_duplicate_effect():\n'
            + '    outcome = execute_synthetic_crash({"public": PUBLIC, "private_simulator": PRIVATE}, PLAN)\n'
            + '    assert outcome["oracle"]["correct_state"], (\n'
            + '        "Retry caused an externally observable correctness violation; "\n'
            + '        f"effects={outcome[\'oracle\'][\'effect_count\']} "\n'
            + '        f"expected={outcome[\'oracle\'][\'expected_count\']}"\n'
            + '    )\n')


def repair_check(report: dict, contract: dict) -> dict:
    """Demonstrate a narrow in-memory idempotency remediation without modifying files."""
    plan = validate_plan(report["plan"], contract)
    before = execute_synthetic_crash(contract, plan)
    corrected = json.loads(canonical(contract))
    corrected["private_simulator"][plan["operation_id"]]["dedupe"] = "request_key"
    after = execute_synthetic_crash(corrected, plan)
    return {"operation_id": plan["operation_id"],
            "before": before["oracle"], "after": after["oracle"],
            "before_failed": not before["oracle"]["correct_state"],
            "after_passed": bool(after["oracle"]["correct_state"]),
            "remediation": "Synthetic adapter now deduplicates by request_key; not an automatic production fix"}


def export_receipt(report_path: str | Path, contract_path: str | Path, output_path: str | Path) -> dict:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    contract = load_contract(contract_path)
    source = make_test_source(report, contract)
    target = Path(output_path)
    if target.suffix != ".py" or not target.name.startswith("test_"):
        raise ValueError("Output must be a test_*.py file")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Never silently replace a potentially modified hand-reviewed regression.
    if target.exists():
        raise FileExistsError(str(target))
    target.write_text(source, encoding="utf-8")
    verification = repair_check(report, contract)
    return {"test_file": str(target), "sha256": sha256(source.encode()).hexdigest(),
            "verification": verification}


def main() -> None:
    parser = argparse.ArgumentParser(description="CrashLab: export an executable synthetic regression")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(json.dumps(export_receipt(args.receipt, args.contract, args.out), indent=2))


if __name__ == "__main__":
    main()
