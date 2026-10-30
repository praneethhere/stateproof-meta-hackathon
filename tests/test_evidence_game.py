import itertools
import json
import pytest
from stateproof.evidence_game import (
    Case, SPECS, SyntheticService, Episode, EvidenceError,
    grounded_verdict, score, baseline_report, cohort, baseline,
)
from stateproof.evidence_meta import run_muse


def test_all_worlds_have_same_client_success_claim():
    for case in SPECS:
        ep = Episode(case, "probe")
        assert ep.public_view()["agent_reported_status"] == "success"
        assert "variant" not in str(ep.public_view())
        assert "truth" not in str(ep.public_view())
        ep.close()


def test_hidden_outcomes_are_real_sqlite_state():
    for case in SPECS:
        svc = SyntheticService(case)
        assert svc.truth() == ("VERIFIED" if case.variant == "good" else "FAILED")
        svc.close()


def test_identical_cheap_order_probe_opposite_outcomes():
    good, bad = Episode(Case("order", "good"), "one"), Episode(Case("order", "unfulfilled"), "two")
    try:
        assert good.inspect("charge_count")["evidence"] == bad.inspect("charge_count")["evidence"]
        assert grounded_verdict(good) == "INCONCLUSIVE"
        assert grounded_verdict(bad) == "INCONCLUSIVE"
        assert good.inspect("fulfillment_count")["evidence"] != bad.inspect("fulfillment_count")["evidence"]
        assert grounded_verdict(good) == "VERIFIED"
        assert grounded_verdict(bad) == "FAILED"
    finally:
        good.close(); bad.close()


def test_cheap_order_probe_can_expose_duplicate_but_not_full_success():
    ep = Episode(Case("order", "duplicate"), "x")
    try:
        ep.inspect("charge_count")
        assert grounded_verdict(ep) == "FAILED"
        assert score(ep, "FAILED")["grounded"]
    finally:
        ep.close()


def test_rollout_ci_success_not_runtime_success():
    a, b = Episode(Case("rollout", "good"), "a"), Episode(Case("rollout", "stale"), "b")
    try:
        assert a.inspect("ci_status")["evidence"] == b.inspect("ci_status")["evidence"]
        assert grounded_verdict(a) == grounded_verdict(b) == "INCONCLUSIVE"
    finally:
        a.close(); b.close()


def test_partner_unavailable_is_not_failure_evidence():
    for variant in ("good", "unsettled"):
        ep = Episode(Case("refund", variant, "partner_down"), "case")
        try:
            obs = ep.inspect("settlement_state")
            assert obs["evidence"]["state"] == "UNAVAILABLE"
            assert grounded_verdict(ep) == "INCONCLUSIVE"
            assert score(ep, "FAILED")["unsupported_assertion"]
            assert score(ep, "INCONCLUSIVE")["grounded"]
        finally:
            ep.close()


def test_all_cases_start_undetermined():
    for _, case in cohort():
        ep = Episode(case, "x")
        assert grounded_verdict(ep) == "INCONCLUSIVE"
        ep.close()


def test_probe_validation_cost_budget_and_no_repetition():
    ep = Episode(Case("order", "good"), "x")
    try:
        with pytest.raises(EvidenceError): ep.inspect("full_audit")
        with pytest.raises(EvidenceError): ep.inspect("__dict__")
        with pytest.raises(EvidenceError): ep.inspect(["charge_count"])
        assert ep.remaining == 3
        ep.inspect("charge_count")
        with pytest.raises(EvidenceError): ep.inspect("charge_count")
        ep.inspect("fulfillment_count")
        assert ep.remaining == 0
        with pytest.raises(EvidenceError): ep.inspect("full_audit")
    finally:
        ep.close()


def test_baselines_no_unsupported_accusations():
    r = baseline_report()
    assert r["status"] == "SYNTHETIC_OFFLINE_PREFLIGHT_NOT_MODEL_RESULTS"
    assert len(cohort()) == 9
    for strategy in r["results"].values():
        assert strategy["cases"] == 9
        assert strategy["unsupported_assertions"] == 0
        assert strategy["grounded"] == 9


def test_contract_aware_still_abstains_when_readback_unavailable():
    for case in (Case("refund", "good", "partner_down"), Case("refund", "unsettled", "partner_down")):
        _, result = baseline(case, "x", "contract_aware")
        assert result["claimed_status"] == "INCONCLUSIVE"


def test_opaque_ids_reproducible_for_seed():
    assert cohort(21) == cohort(21)
    assert cohort(22) != cohort(21)


class FakeUsage:
    input_tokens = 10
    output_tokens = 20

class FakeItem:
    type = "function_call"
    def __init__(self, name, arguments, call_id):
        self.name, self.arguments, self.call_id = name, json.dumps(arguments), call_id

class FakeResponse:
    usage = FakeUsage()
    output_text = ""
    def __init__(self, response_id, output):
        self.id, self.output = response_id, output

class FakeClient:
    def __init__(self, responses):
        self.calls = []
        self.responses = iter(responses)
        self.responses_api = self
        self.responses = self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.iterator)

class StubClient:
    def __init__(self, items):
        self.iterator = iter(items)
        self.calls = []
        self.responses = self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.iterator)


def test_tool_loop_executes_without_private_oracle_leak():
    client = StubClient([
        FakeResponse("r1", [FakeItem("inspect_evidence", {"probe_id": "charge_count"}, "c1")]),
        FakeResponse("r2", [FakeItem("inspect_evidence", {"probe_id": "fulfillment_count"}, "c2")]),
        FakeResponse("r3", [FakeItem("submit_verdict", {"verdict": "VERIFIED", "explanation": "one of each"}, "c3")]),
    ])
    r = run_muse(Case("order", "good"), "local", client=client)
    assert r["grounded"]
    assert r["claimed_status"] == "VERIFIED"
    assert r["model_executed_probe"]
    assert len(client.calls) == 3
    assert client.calls[1]["previous_response_id"] == "r1"
    assert client.calls[2]["previous_response_id"] == "r2"
    for k in client.calls:
        assert '"variant"' not in str(k["input"])
        assert '"true_status"' not in str(k["input"])
        assert '"private' not in str(k["input"])


def test_reject_unknown_probe_without_spending_budget():
    client = StubClient([
        FakeResponse("r1", [FakeItem("inspect_evidence", {"probe_id": "full_audit"}, "c1")]),
        FakeResponse("r2", [FakeItem("submit_verdict", {"verdict": "INCONCLUSIVE", "explanation": "no evidence"}, "c2")]),
    ])
    r = run_muse(Case("order", "good"), "local", client=client)
    assert not r["tool_calls"][0]["accepted"]
    assert r["cost"] == 0
    assert r["grounded"]


def test_invalid_model_submission_never_counts_as_success():
    client = StubClient([
        FakeResponse("r1", [FakeItem("submit_verdict", {"verdict": "FAILED", "explanation": "guess"}, "c1")]),
    ])
    r = run_muse(Case("order", "good"), "local", client=client)
    assert r["unsupported_assertion"]
    assert not r["grounded"]
