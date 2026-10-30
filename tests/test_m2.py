import json
from types import SimpleNamespace
import pytest
from stateproof.experiments import (
    FAULTS, PROBES, PUBLIC_CONTRACTS, InvalidExperiment, Selection, Sandbox,
    ExperimentBudget, fixed_baseline, random_baseline, validate_selection, verify_effects,
)
from stateproof.meta_investigator import investigate, _call_kwargs


@pytest.mark.parametrize("fault", FAULTS)
@pytest.mark.parametrize("probe", PROBES)
def test_valid_arguments(fault, probe):
    assert validate_selection({"fault_id": fault, "probe_id": probe}) == Selection(fault, probe)


@pytest.mark.parametrize("invalid", [None, [], {}, {"fault_id": "lost_ack", "probe_id": "effect_ids", "cmd": "rm -rf /"},
                                       {"fault_id": "rm -rf /", "probe_id": "effect_ids"},
                                       {"fault_id": "lost_ack", "probe_id": ["effect_ids"]},
                                       {"fault_id": False, "probe_id": "effect_ids"}])
def test_rejects_bad_arguments(invalid):
    with pytest.raises(InvalidExperiment):
        validate_selection(invalid)


@pytest.mark.parametrize("target, fault, failing", [
    ("gateway", "lost_ack", True), ("gateway", "stale_read", False),
    ("cache", "stale_read", True), ("cache", "lost_ack", False),
    ("orchestrator", "partial_commit", True), ("orchestrator", "lost_ack", False),
    ("healthy", "lost_ack", False), ("healthy", "stale_read", False),
    ("healthy", "partial_commit", False), ("healthy", "clean", False),
])
def test_injected_faults(target, fault, failing):
    r = Sandbox(target).run(Selection(fault, "effect_ids"))
    assert (r["private_evidence"]["oracle"]["verdict"] == "FAIL") is failing
    assert r["private_evidence"]["observable_failure"] is failing


def test_oracle_independent_of_probe():
    r = Sandbox("orchestrator").run(Selection("partial_commit", "ledger_count"))
    assert r["private_evidence"]["oracle"]["verdict"] == "FAIL"
    assert r["private_evidence"]["observable_failure"] is False


def test_budget_and_unique_faults():
    b = ExperimentBudget("gateway", 1)
    b.execute({"fault_id": "clean", "probe_id": "effect_ids"})
    with pytest.raises(InvalidExperiment):
        b.execute({"fault_id": "lost_ack", "probe_id": "effect_ids"})
    b = ExperimentBudget("gateway", 2)
    b.execute({"fault_id": "clean", "probe_id": "effect_ids"})
    with pytest.raises(InvalidExperiment):
        b.execute({"fault_id": "clean", "probe_id": "ledger_count"})


def test_sandbox_isolation():
    a = Sandbox("gateway").run(Selection("lost_ack", "effect_ids"))
    b = Sandbox("gateway").run(Selection("clean", "effect_ids"))
    assert a["private_evidence"]["oracle"]["charge_count"] == 2
    assert b["private_evidence"]["oracle"]["charge_count"] == 1


def test_no_private_oracle_visible_to_model():
    b = ExperimentBudget("gateway")
    observation = b.execute({"fault_id": "lost_ack", "probe_id": "effect_ids"})
    assert "private_evidence" not in observation
    assert "oracle" not in json.dumps(observation)


def test_fixed_and_seeded_baselines_reproducible():
    assert fixed_baseline("gateway") == fixed_baseline("gateway")
    assert random_baseline("cache", 19) == random_baseline("cache", 19)


def _response(output, *, text="", rid="response1", tokens=5):
    return SimpleNamespace(status="completed", output=output, output_text=text, id=rid,
                           usage=SimpleNamespace(input_tokens=tokens, output_tokens=tokens))


def _tool(args, call_id="call1", name="run_experiment"):
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(args), call_id=call_id)


class FakeResponses:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


class FakeClient:
    def __init__(self, replies):
        self.responses = FakeResponses(replies)


def test_real_shape_function_call_loop_without_network():
    client = FakeClient([
        _response([_tool({"fault_id": "partial_commit", "probe_id": "effect_ids"})]),
        _response([], text="I found missing fulfillment", rid="response2"),
    ])
    receipt = investigate("orchestrator", budget=1, client=client)
    assert receipt["verified_model_tool_execution"] is True
    assert receipt["observable_detections"] == 1
    assert receipt["api_usage"] == {"input_tokens": 10, "output_tokens": 10}
    assert client.responses.calls[0]["parallel_tool_calls"] is False
    assert client.responses.calls[1]["previous_response_id"] == "response1"
    assert client.responses.calls[1]["input"][0]["type"] == "function_call_output"


def test_model_no_tool_not_claimed_verified():
    client = FakeClient([_response([], text="No tools", rid="r0")])
    receipt = investigate("gateway", client=client)
    assert receipt["verified_model_tool_execution"] is False
    assert receipt["termination"] == "model_final_no_tool"
    assert receipt["experiments_used"] == 0


def test_bad_model_arguments_rejected_no_experiment():
    client = FakeClient([
        _response([_tool({"fault_id": "lost_ack", "probe_id": "effect_ids", "sql": "DROP TABLE"})]),
        _response([], text="stop", rid="r2"),
    ])
    receipt = investigate("gateway", client=client)
    assert receipt["experiments_used"] == 0
    assert receipt["tool_calls"][0]["accepted"] is False


def test_investigator_caps_budget_even_if_model_wants_more():
    client = FakeClient([
        _response([_tool({"fault_id": "lost_ack", "probe_id": "effect_ids"})]),
        _response([_tool({"fault_id": "partial_commit", "probe_id": "effect_ids"}, "call2")]),
    ])
    receipt = investigate("gateway", budget=1, client=client)
    assert receipt["experiments_used"] == 1
    assert receipt["termination"] == "budget_exhausted"
    assert len(client.responses.calls) == 2


def test_investigator_turn_cap():
    client = FakeClient([
        _response([_tool({"fault_id": "clean", "probe_id": "ledger_count"})]),
    ])
    receipt = investigate("healthy", budget=2, max_turns=1, client=client)
    assert receipt["termination"] == "max_turns"
    assert receipt["experiments_used"] == 1
