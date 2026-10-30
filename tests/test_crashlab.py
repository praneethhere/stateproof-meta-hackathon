"""Offline-only: no tests call the Meta API."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stateproof.crashlab import (
    baseline_plan, candidate_ids, digest, execute_synthetic_crash, load_contract,
    muse_plan, public_contract, render_html, run_local, validate_plan,
)

CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "support_credit.json"


@pytest.fixture
def data():
    return load_contract(CONTRACT)


def test_load(data):
    assert len(candidate_ids(data)) == 3


def test_only_public_is_exposed(data):
    assert "private_simulator" not in public_contract(data)


def test_idempotent_initial_write_is_safe(data):
    report = run_local(data, "writes_first")
    assert report["plan"]["operation_id"] == "open_case"
    assert not report["result"]["false_success"]
    assert report["result"]["oracle"]["effect_count"] == 1


def test_nonidempotent_postcommit_duplicate(data):
    plan = {"operation_id": "apply_credit", "phase": "after_commit_lost_ack",
            "hypothesis": "credit can be duplicated", "readback": "check credit ledger"}
    result = execute_synthetic_crash(data, plan)
    assert result["actor"] == "deterministic_bounded_retry_client"
    assert result["false_success"]
    assert result["oracle"]["effect_count"] == 2
    assert [e["committed"] for e in result["events"]] == [True, True]


@pytest.mark.parametrize("op", ["open_case", "apply_credit", "notify_customer"])
def test_before_commit_timeout_is_safe(data, op):
    plan = {"operation_id": op, "phase": "before_commit_timeout",
            "hypothesis": "check timeout", "readback": "ledger"}
    assert execute_synthetic_crash(data, plan)["oracle"]["effect_count"] == 1


def test_no_fault_only_one(data):
    plan = {"operation_id": "apply_credit", "phase": "no_fault",
            "hypothesis": "check", "readback": "ledger"}
    assert execute_synthetic_crash(data, plan)["oracle"]["effect_count"] == 1


def test_keyword_heuristic_is_strong_baseline(data):
    assert baseline_plan(data, "keyword")["operation_id"] == "apply_credit"


def test_random_reproducible(data):
    assert baseline_plan(data, "random", seed=12) == baseline_plan(data, "random", seed=12)


@pytest.mark.parametrize("bad", [
    {"operation_id": "delete_all", "phase": "after_commit_lost_ack", "hypothesis": "x", "readback": "y"},
    {"operation_id": "apply_credit", "phase": "shell", "hypothesis": "x", "readback": "y"},
    {"operation_id": "apply_credit", "phase": "after_commit_lost_ack", "hypothesis": "x", "readback": "y", "command": "rm -rf /"},
    {"operation_id": "apply_credit", "phase": "after_commit_lost_ack", "hypothesis": "", "readback": "y"},
])
def test_plan_rejects_unsafe(bad, data):
    with pytest.raises(ValueError):
        validate_plan(bad, data)


def test_validate_duplicate_ids(data):
    c = copy.deepcopy(data)
    c["public"]["operations"].append(c["public"]["operations"][0])
    p = Path('/tmp/crashlab-bad-ids-test.json')
    try:
        p.write_text(json.dumps(c))
        with pytest.raises(ValueError):
            load_contract(p)
    finally:
        p.unlink(missing_ok=True)


class FakeClient:
    def __init__(self, obj):
        self.obj = obj
        self.request = None
        self.responses = self

    def create(self, **kwargs):
        self.request = kwargs
        call = SimpleNamespace(type="function_call", name="submit_crash_plan",
                               arguments=json.dumps(self.obj))
        return SimpleNamespace(output=[call], usage=SimpleNamespace(input_tokens=100, output_tokens=40))


def test_model_tool_plan_and_private_hidden(data):
    expected = {"operation_id": "apply_credit", "phase": "after_commit_lost_ack",
                "hypothesis": "lost ack can double credit", "readback": "credit ledger"}
    client = FakeClient(expected)
    plan, usage = muse_plan(data, client=client)
    assert plan == expected
    assert usage == {"input_tokens": 100, "output_tokens": 40}
    sent = client.request["input"]
    assert "private_simulator" not in sent
    assert "severity" not in sent
    assert "dedupe" not in sent or "deduplication" in sent  # docs are allowed
    assert client.request["reasoning"]["effort"] == "high"
    assert run_local(data, "muse", client=client)["result"]["false_success"]


def test_model_invalid_operation_stopped(data):
    client = FakeClient({"operation_id": "arbitrary_code", "phase": "no_fault",
                         "hypothesis": "run", "readback": "ledger"})
    with pytest.raises(ValueError):
        muse_plan(data, client=client)


def test_render_escapes_hypothesis(data):
    report = run_local(data, "writes_first")
    report["plan"]["hypothesis"] = '<script>alert("x")</script>'
    page = render_html(report)
    assert "&lt;script&gt;" in page
    assert '<script>alert("x")</script>' not in page


def test_receipt_contains_truth_labeled_private(data):
    r = run_local(data, "keyword")
    assert "oracle" in r["result"]
    assert len(r["receipt_sha256"]) == 64
    assert len(digest(public_contract(data))) == 64


def test_no_extra_call_strategy_allowed(data):
    with pytest.raises(ValueError):
        baseline_plan(data, "evil")


def test_repeated_fresh_sqlite(data):
    a, b = run_local(data, "keyword"), run_local(data, "keyword")
    assert a["result"]["oracle"] == b["result"]["oracle"]
