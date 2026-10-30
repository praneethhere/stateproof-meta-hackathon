"""Prebuild prototype checks: hidden outcomes must not leak through traces."""
import json
import pytest
from stateproof.experiments import Sandbox, Selection, ExperimentBudget, public_prompt

BANNED = ("charge_committed", "retry_committed_second_charge", "fulfillment_recorded", "fulfillment_step_not_committed")

@pytest.mark.parametrize("target", ["gateway", "cache", "orchestrator", "healthy"])
@pytest.mark.parametrize("fault", ["lost_ack", "stale_read", "partial_commit", "clean"])
@pytest.mark.parametrize("probe", ["ledger_count", "order_status", "effect_ids"])
def test_no_outcome_leak_through_trace(target, fault, probe):
    r = Sandbox(target).run(Selection(fault, probe))
    text = json.dumps(r["model_visible"])
    assert not any(marker in text for marker in BANNED)
    assert "private_evidence" not in text
    assert "oracle" not in text
    assert "verdict" not in text


def test_same_observation_opposite_oracles():
    selection = Selection("partial_commit", "ledger_count")
    flawed = Sandbox("orchestrator", repaired=False).run(selection)
    fixed = Sandbox("orchestrator", repaired=True).run(selection)
    assert flawed["model_visible"] == fixed["model_visible"]
    assert flawed["private_evidence"]["oracle"]["verdict"] == "FAIL"
    assert fixed["private_evidence"]["oracle"]["verdict"] == "PASS"
    assert flawed["private_evidence"]["observable_failure"] is False


def test_sufficient_probe_distinguishes_counterfactuals():
    selection = Selection("partial_commit", "effect_ids")
    flawed = Sandbox("orchestrator", repaired=False).run(selection)
    fixed = Sandbox("orchestrator", repaired=True).run(selection)
    assert flawed["model_visible"]["trace"] == fixed["model_visible"]["trace"]
    assert flawed["model_visible"]["probe_result"] != fixed["model_visible"]["probe_result"]
    assert flawed["private_evidence"]["observable_failure"] is True
    assert fixed["private_evidence"]["observable_failure"] is False


def test_unseen_oracle_failure_counted_as_probe_miss():
    budget = ExperimentBudget("orchestrator", 1)
    obs = budget.execute({"fault_id": "partial_commit", "probe_id": "ledger_count"})
    assert "oracle" not in json.dumps(obs)
    receipt = budget.summary("test")
    assert receipt["violation_experiments"] == 1
    assert receipt["observable_detections"] == 0
    assert receipt["oracle_fail_probe_misses"] == 1


def test_inconclusive_rule_explicit():
    prompt = public_prompt("orchestrator", 1)
    assert "INCONCLUSIVE" in prompt
    assert "Do not infer committed side effects" in prompt
