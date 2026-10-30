"""Oct 29 M2.6: offline negative control for the evidence gate.

A synthetic candidate verdict is deliberately submitted with inadequate readback.
It is NOT a Muse-produced assertion. No real systems or provider API are accessed.
"""
from __future__ import annotations
from .evidence_game import Episode, cohort
from .evidence_gate import gate_verdict, proof_chain

WEAK_PROBES = {"order": "charge_count", "rollout": "ci_status", "refund": "processor_ack"}


def run_negative_control(index: int) -> dict:
    cases = cohort()
    if type(index) is not int or not 0 <= index < len(cases):
        raise ValueError("Invalid synthetic case index")
    case_id, case = cases[index]
    ep = Episode(case, case_id)
    try:
        probe = WEAK_PROBES[case.workflow]
        readback = ep.inspect(probe)
        observed_status = gate_verdict(case.workflow, ep.records)
        attempted = "VERIFIED"
        # A sound gate must not accept a verdict unsupported by its own readback.
        if observed_status == attempted:
            raise AssertionError("Negative control unexpectedly sufficient")
        evidence = list(ep.records)
        return {
            "mode": "offline_negative_control",
            "label": "Deliberately unsupported candidate (NOT a Muse output)",
            "case_id": case_id,
            "workflow": case.workflow,
            "agent_reported_status": "success",
            "attempted_verdict": attempted,
            "gate_supported_status": observed_status,
            "gate_accepted": False,
            "rejection_reason": "Candidate VERIFIED is not supported by independent available evidence.",
            "evidence_receipts": evidence,
            "receipt_chain": proof_chain(case_id, evidence),
            "probe_cost": readback["cost"],
            "remaining_budget": ep.remaining,
            "api_usage": {"input_tokens": 0, "output_tokens": 0},
            "model_calls": 0,
            "replay_disclosure": "Offline synthetic negative control; no Meta model generated the rejected verdict.",
        }
    finally:
        ep.close()
