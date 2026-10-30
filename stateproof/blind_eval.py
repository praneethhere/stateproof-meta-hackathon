"""PREBUILD DESIGN CHECK — blind, paired synthetic evaluation; not a hackathon submission claim.

No API calls. Only probe observations may go to an agent. Private oracle and scenario
implementation are accessible to the OFFLINE scorer, never to the model/tool output.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import random
from typing import Iterable

from .experiments import FAULTS, PROBES, PUBLIC_CONTRACTS, Sandbox, Selection, validate_selection

PUBLIC_TASK = (
    "An order-processing agent accepts a $25 purchase request. Its contract requires "
    "exactly one charge and exactly one fulfillment record. It uses retries and "
    "multi-step tools, and may encounter a transient interruption. "
    "The implementation and outcome of any write are UNKNOWN. "
    "Investigate with approved fault injections and read-back probes. "
    "A suspicious trace alone is not proof of an external effect."
)

@dataclass(frozen=True)
class _HiddenCase:
    opaque_id: str
    implementation: str
    repaired: bool


def _cases(seed: int) -> tuple[_HiddenCase, ...]:
    """Stable opaque IDs with seeded permutation, unknown to the investigator."""
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    # Each implementation appears with both repaired and faulty variants.
    specs = [(name, repaired) for name in PUBLIC_CONTRACTS for repaired in (True, False)]
    random.Random(seed).shuffle(specs)
    return tuple(
        _HiddenCase(
            opaque_id="case-" + hashlib.sha256(f"{seed}:{index}".encode()).hexdigest()[:10],
            implementation=name,
            repaired=repaired,
        )
        for index, (name, repaired) in enumerate(specs)
    )


class BlindCohort:
    """Model-visible interface: public_case_ids(), describe(), observe().

    Private methods whose names begin with _ should be used only by the scorer.
    Never serialize the object or its private mappings to a model prompt.
    """
    def __init__(self, seed: int = 20261027):
        self._cases = {c.opaque_id: c for c in _cases(seed)}
        self._records: list[dict] = []

    def public_case_ids(self) -> tuple[str, ...]:
        return tuple(self._cases)

    def describe(self, opaque_id: str) -> dict:
        self._require(opaque_id)
        return {"case_id": opaque_id, "contract": PUBLIC_TASK,
                "available_faults": list(FAULTS), "available_probes": list(PROBES)}

    def _require(self, opaque_id: str) -> _HiddenCase:
        if type(opaque_id) is not str or opaque_id not in self._cases:
            raise ValueError("Unknown case ID")
        return self._cases[opaque_id]

    def observe(self, opaque_id: str, arguments: dict) -> dict:
        """Model-safe tool result (no private oracle, no implementation labels)."""
        selection = validate_selection(arguments)
        case = self._require(opaque_id)
        result = Sandbox(case.implementation, repaired=case.repaired).run(selection)
        self._records.append({"case_id": opaque_id, "selection": arguments, "result": result})
        return {"case_id": opaque_id, **result["model_visible"]}

    def _private_truth(self, opaque_id: str) -> dict:
        """Scorer-only access. Never include in model-visible payloads."""
        case = self._require(opaque_id)
        return {"implementation": case.implementation, "repaired": case.repaired}

    def _private_score(self, opaque_id: str, selections: Iterable[dict]) -> dict:
        """Scorer replay uses the same sandbox and independent oracle."""
        case = self._require(opaque_id)
        selections = list(selections)
        if len(selections) > 4:
            raise ValueError("Too many experiments")
        seen = set()
        detected = False
        for args in selections:
            choice = validate_selection(args)
            if choice.fault_id in seen:
                raise ValueError("Repeated fault in an episode")
            seen.add(choice.fault_id)
            evidence = Sandbox(case.implementation, repaired=case.repaired).run(choice)
            detected |= bool(evidence["private_evidence"]["observable_failure"])
        # Exhaustive use of a complete probe is OFFLINE GROUND TRUTH, not a runnable baseline.
        actually_vulnerable = any(
            Sandbox(case.implementation, repaired=case.repaired)
            .run(Selection(fault, "effect_ids"))["private_evidence"]["oracle"]["verdict"] == "FAIL"
            for fault in FAULTS
        )
        return {"case_id": opaque_id, "vulnerable": actually_vulnerable,
                "detected": detected, "false_positive": detected and not actually_vulnerable,
                "missed_vulnerability": actually_vulnerable and not detected}


def baseline_report(seed: int = 20261027, budget: int = 2) -> dict:
    """Offline-only comparison at equal experiment count, same full-evidence probe.

    These deliberately simple baselines reveal whether the current test suite favors
    any method. The private truth and report must not be passed to Muse.
    """
    if type(budget) is not int or budget < 1 or budget > len(FAULTS):
        raise ValueError("budget must be 1..4")
    cohort = BlindCohort(seed)
    strategies = {
        "fixed_order": list(FAULTS)[:budget],
        "fixed_alternative": ["partial_commit", "stale_read", "lost_ack", "clean"][:budget],
        "seeded_random": random.Random(seed).sample(list(FAULTS), budget),
    }
    results = {}
    for name, faults in strategies.items():
        selections = [{"fault_id": f, "probe_id": "effect_ids"} for f in faults]
        cases = [cohort._private_score(cid, selections) for cid in cohort.public_case_ids()]
        results[name] = {
            "budget": budget,
            "faults": faults,
            "true_positives": sum(x["detected"] and x["vulnerable"] for x in cases),
            "false_positives": sum(x["false_positive"] for x in cases),
            "false_negatives": sum(x["missed_vulnerability"] for x in cases),
            "true_negatives": sum(not x["detected"] and not x["vulnerable"] for x in cases),
        }
    return {"status": "PREBUILD_OFFLINE_ONLY", "cases": len(cohort.public_case_ids()),
            "vulnerable_cases": sum(cohort._private_score(cid, [])["vulnerable"] for cid in cohort.public_case_ids()),
            "clean_cases": sum(not cohort._private_score(cid, [])["vulnerable"] for cid in cohort.public_case_ids()),
            "strategies": results,
            "limitations": [
                "Existing synthetic implementations reused as private variants; NOT independent held-out workflows.",
                "All strategies use the universally sufficient effect_ids probe at equal cost.",
                "This is a leakage/negative-control exercise, not proof that models outperform baselines.",
                "Do not provide private truth or this scorer output to the model during evaluation.",
            ]}


if __name__ == "__main__":
    print(json.dumps(baseline_report(), indent=2))
