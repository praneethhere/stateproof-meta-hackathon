"""Synthetic, isolated agent-effect experiments. No real payment calls.

This is a competition PREVIEW harness, not evidence that an AI model found a bug.
The private oracle is intentionally separate from the model-visible observation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import random
import sqlite3
from typing import Any

FAULTS = ("lost_ack", "stale_read", "partial_commit", "clean")
PROBES = ("ledger_count", "order_status", "effect_ids")

# Descriptions are intentionally indicative but do not announce hidden faults.
PUBLIC_CONTRACTS = {
    "gateway": "A legacy gateway adapter writes an order payment. On a transport timeout, the caller may retry. The adapter's idempotency behavior is undocumented.",
    "cache": "Order state reads pass through a cache that may lag behind writes. The retry client uses state reads to decide whether a payment finished.",
    "orchestrator": "Order completion consists of payment then fulfillment registration. The agent-facing API may return a summary after partial interruption.",
    "healthy": "Idempotency keys are enforced, state reads are monotonic, and payment plus fulfillment is transactional.",
}


class InvalidExperiment(ValueError):
    pass


@dataclass(frozen=True)
class Selection:
    fault_id: str
    probe_id: str


def validate_selection(args: Any) -> Selection:
    """Reject unknown keys, wrong types, and non-allowlisted values (never coerce)."""
    if not isinstance(args, dict) or set(args) != {"fault_id", "probe_id"}:
        raise InvalidExperiment("Arguments must contain only fault_id and probe_id")
    fault, probe = args["fault_id"], args["probe_id"]
    if type(fault) is not str or fault not in FAULTS:
        raise InvalidExperiment("fault_id is not allowlisted")
    if type(probe) is not str or probe not in PROBES:
        raise InvalidExperiment("probe_id is not allowlisted")
    return Selection(fault, probe)


def _new_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE effects (seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, amount_cents INTEGER NOT NULL)")
    return db


def _effect(db: sqlite3.Connection, kind: str, cents: int) -> None:
    db.execute("INSERT INTO effects (kind, amount_cents) VALUES (?,?)", (kind, cents))
    db.commit()


def _read(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute("SELECT seq,kind,amount_cents FROM effects ORDER BY seq").fetchall()
    return [{"seq": n, "kind": k, "amount_cents": c} for n, k, c in rows]


def _visible_probe(probe: str, effects: list[dict]) -> dict:
    if probe == "ledger_count":
        return {"charge_count": sum(e["kind"] == "charge" for e in effects)}
    if probe == "order_status":
        return {"paid": any(e["kind"] == "charge" for e in effects),
                "fulfilled": any(e["kind"] == "fulfillment" for e in effects)}
    if probe == "effect_ids":
        return {"effects": [{"seq": e["seq"], "kind": e["kind"]} for e in effects]}
    raise AssertionError("validated before invocation")


def _observable_failure(probe: str, observation: dict, reported_status: str) -> bool:
    """Conservative visible detection rule; may miss issues not visible to a probe."""
    if probe == "ledger_count":
        return observation["charge_count"] != 1
    if probe == "order_status":
        return reported_status == "success" and (not observation["paid"] or not observation["fulfilled"])
    if probe == "effect_ids":
        kinds = [e["kind"] for e in observation["effects"]]
        return kinds.count("charge") != 1 or kinds.count("fulfillment") != 1
    return False


class Sandbox:
    """An independent fresh SQLite database is used for EVERY test."""
    def __init__(self, target: str, *, repaired: bool = False):
        if type(repaired) is not bool:
            raise ValueError("repaired must be a boolean")
        self.repaired = repaired
        if target not in PUBLIC_CONTRACTS:
            raise ValueError("Unsupported synthetic target")
        self.target = target

    def run(self, selection: Selection) -> dict:
        if selection.fault_id not in FAULTS or selection.probe_id not in PROBES:
            raise InvalidExperiment("Illegal selection")
        db = _new_db()
        try:
            # OBSERVATION BOUNDARY: The trace describes client-visible operations only.
            # Never append hidden database outcome labels (e.g. "fulfillment_not_committed").
            # Repaired and broken implementations may therefore be indistinguishable
            # to a weak probe, even when their independent oracle verdicts differ.
            trace = ["payment_request_sent"]
            _effect(db, "charge", 2500)
            duplicate = ((self.target == "gateway" and selection.fault_id == "lost_ack") or
                         (self.target == "cache" and selection.fault_id == "stale_read")) and not self.repaired
            omitted = (self.target == "orchestrator" and selection.fault_id == "partial_commit"
                       and not self.repaired)
            if selection.fault_id == "lost_ack":
                trace += ["payment_response_timeout", "retry_request_sent"]
            elif selection.fault_id == "stale_read":
                trace += ["payment_state_read_unconfirmed", "retry_request_sent"]
            elif selection.fault_id == "partial_commit":
                trace += ["fulfillment_request_sent", "orchestration_timeout"]
            else:
                trace += ["payment_response_received", "fulfillment_request_sent"]
            if duplicate:
                _effect(db, "charge", 2500)
            if not omitted:
                _effect(db, "fulfillment", 0)
            effects = _read(db)
            oracle = verify_effects(effects)
            visible = _visible_probe(selection.probe_id, effects)
            detected = _observable_failure(selection.probe_id, visible, "success")
            return {
                "selection": {"fault_id": selection.fault_id, "probe_id": selection.probe_id},
                "model_visible": {"reported_status": "success", "trace": trace,
                                  "probe_id": selection.probe_id, "probe_result": visible},
                "private_evidence": {"effects": effects, "oracle": oracle, "observable_failure": detected,
                                     "oracle_fail_but_probe_misses": oracle["verdict"] == "FAIL" and not detected},
            }
        finally:
            db.close()


def verify_effects(effects: list[dict]) -> dict:
    """External-state oracle: exactly one $25 charge and one fulfillment."""
    charges = [e for e in effects if e["kind"] == "charge"]
    fulfillments = [e for e in effects if e["kind"] == "fulfillment"]
    good = (len(charges) == 1 and charges[0]["amount_cents"] == 2500
            and len(fulfillments) == 1 and fulfillments[0]["amount_cents"] == 0)
    return {"verdict": "PASS" if good else "FAIL",
            "charge_count": len(charges), "fulfillment_count": len(fulfillments),
            "charged_cents": sum(e["amount_cents"] for e in charges),
            "expected_charge_count": 1, "expected_fulfillment_count": 1,
            "expected_charged_cents": 2500}


class ExperimentBudget:
    def __init__(self, target: str, budget: int = 2):
        if type(budget) is not int or not 1 <= budget <= 4:
            raise ValueError("Budget must be integer 1..4")
        self.target = target
        self.budget = budget
        self.results: list[dict] = []
        self.seen: set[str] = set()

    @property
    def remaining(self) -> int:
        return self.budget - len(self.results)

    def execute(self, args: dict) -> dict:
        s = validate_selection(args)
        if not self.remaining:
            raise InvalidExperiment("Experiment budget exhausted")
        if s.fault_id in self.seen:
            raise InvalidExperiment("Fault already tested in this trial")
        result = Sandbox(self.target).run(s)
        self.results.append(result)
        self.seen.add(s.fault_id)
        # Only the observation is returned to the model, NOT the private oracle.
        return result["model_visible"]

    def summary(self, strategy: str) -> dict:
        findings = [r for r in self.results if r["private_evidence"]["oracle"]["verdict"] == "FAIL"]
        detected = [r for r in findings if r["private_evidence"]["observable_failure"]]
        return {
            "target": self.target, "strategy": strategy, "budget": self.budget,
            "experiments_used": len(self.results), "violation_experiments": len(findings),
            "observable_detections": len(detected),
            "oracle_fail_probe_misses": len(findings) - len(detected),
            "evidence_receipts": self.results,
        }


def fixed_baseline(target: str, budget: int = 2, order: tuple[str, ...] = ("lost_ack", "stale_read", "partial_commit", "clean")) -> dict:
    runner = ExperimentBudget(target, budget)
    for fault in order[:budget]:
        runner.execute({"fault_id": fault, "probe_id": "effect_ids"})
    return runner.summary("fixed:" + ",".join(order[:budget]))


def random_baseline(target: str, seed: int, budget: int = 2) -> dict:
    runner = ExperimentBudget(target, budget)
    choices = list(FAULTS)
    random.Random(seed).shuffle(choices)
    for fault in choices[:budget]:
        runner.execute({"fault_id": fault, "probe_id": "effect_ids"})
    result = runner.summary("random_seed_" + str(seed))
    result["seed"] = seed
    return result


def public_prompt(target: str, budget: int) -> str:
    if target not in PUBLIC_CONTRACTS:
        raise ValueError(target)
    return (
        "You are evaluating a SYNTHETIC, isolated $25 order-processing workflow. "
        "The intended invariant is exactly one charge and one fulfillment record; "
        "an agent's reported success is not trusted. "
        "There are four allowed injected fault types: lost_ack, stale_read, partial_commit, clean. "
        "For each experiment choose ONE fault_id and ONE probe_id from: ledger_count, "
        "order_status, effect_ids. Tool results expose only observations; they are not independent proof. "
        "Your objective is to select experiments likely to uncover observable incorrect external effects. "
        "Do not infer committed side effects from timeouts or from an injected fault name. "
        "A request-sent event does not prove a write committed. If a probe cannot establish the "
        "claimed invariant, explicitly state INCONCLUSIVE instead of asserting a failure. "
        "Target public contract: " + PUBLIC_CONTRACTS[target] + "\n"
        f"You may run at most {budget} different experiments; do not repeat a fault_id. "
        "Use run_experiment to investigate, and then give a brief evidence-based conclusion. "
        "If no tool is used, your conclusion must explicitly state no empirical verification was performed."
    )
