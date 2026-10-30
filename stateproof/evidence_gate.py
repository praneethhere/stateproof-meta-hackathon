"""M2.4: public-contract-based post-action evidence gate.

No private world enumeration, oracle, variant, or case truth is used here.
This is an intentionally narrow deterministic verifier, not a generic proof system.
"""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Any

VALID = {"VERIFIED", "FAILED", "INCONCLUSIVE"}


def gate_verdict(workflow: str, observations: list[dict]) -> str:
    """Return the strongest justified conclusion from inspected evidence only."""
    vals: dict[str, Any] = {}
    for receipt in observations:
        if not isinstance(receipt, dict):
            return "INCONCLUSIVE"
        pid = receipt.get("probe_id")
        evidence = receipt.get("evidence")
        if not isinstance(pid, str) or not isinstance(evidence, dict):
            return "INCONCLUSIVE"
        if pid in vals and vals[pid] != evidence:
            return "INCONCLUSIVE"  # contradictory readbacks, never silently pick one
        vals[pid] = evidence

    if workflow == "order":
        charge = vals.get("charge_count", {}).get("charge_count")
        fulfill = vals.get("fulfillment_count", {}).get("fulfillment_count")
        if charge is not None and (type(charge) is not int or charge != 1):
            return "FAILED" if type(charge) is int and charge >= 0 else "INCONCLUSIVE"
        if fulfill is not None and (type(fulfill) is not int or fulfill != 1):
            return "FAILED" if type(fulfill) is int and fulfill >= 0 else "INCONCLUSIVE"
        if type(charge) is int and type(fulfill) is int:
            return "VERIFIED"
        return "INCONCLUSIVE"
    if workflow == "rollout":
        revision = vals.get("runtime_revision", {}).get("revision")
        if type(revision) is not str or not revision:
            return "INCONCLUSIVE"
        return "VERIFIED" if revision == "r2" else "FAILED"
    if workflow == "refund":
        refund = vals.get("settlement_state", {})
        if refund.get("state") == "UNAVAILABLE":
            return "INCONCLUSIVE"
        count, total = refund.get("settled_refunds"), refund.get("total_cents")
        if type(count) is not int or type(total) is not int or count < 0 or total < 0:
            return "INCONCLUSIVE"
        return "VERIFIED" if (count, total) == (1, 2500) else "FAILED"
    raise ValueError("Unknown synthetic workflow")


def proof_chain(case_id: str, observations: list[dict]) -> list[dict]:
    """Tamper-evident local hash chain (not externally signed/authenticated)."""
    previous = "0" * 64
    chain = []
    for i, item in enumerate(observations):
        payload = {"case_id": case_id, "sequence": i, "previous_sha256": previous,
                   "observation": item}
        digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True).encode("utf8")).hexdigest()
        chain.append({"sequence": i, "previous_sha256": previous,
                      "sha256": digest, "observation": item})
        previous = digest
    return chain


def verify_chain(case_id: str, chain: list[dict]) -> bool:
    if not isinstance(chain, list):
        return False
    obs = [x.get("observation") for x in chain if isinstance(x, dict)]
    if len(obs) != len(chain):
        return False
    expected = proof_chain(case_id, obs)
    return chain == expected
