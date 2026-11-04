import json

import pytest
from stateproof.intent_study import grade_plan, structurally_valid
from stateproof.intent_muse import (
    parse_proposal,
    publish_observation,
    ROOT,
)
from stateproof.crashlab import digest


def test_equal_count_can_hide_a_missing_tenant_and_duplicate_peer():
    counted = grade_plan("AABC", "count")
    exact = grade_plan("AABC", "identity_multiset")
    case = next(
        row for row in counted["adapters"] if row["index"] == "request_key+attempt_no"
    )
    assert case["approved"] and not case["reference_valid"]
    assert case["actual"] == [
        ("north", "1", "0"),
        ("north", "1", "0"),
        ("north", "2", "0"),
    ]
    assert counted["expected"] == [
        ("north", "1", "0"),
        ("north", "2", "0"),
        ("south", "1", "0"),
    ]
    assert "request_key+attempt_no" in counted["false_approvals"]
    assert (
        exact["correctly_classified"] == 32
        and not exact["false_approvals"]
        and not exact["false_refusals"]
    )


def test_counterexample_and_valid_equivalent_indexes_are_scored():
    assert structurally_valid(("tenant", "local_intent", "payload"))
    assert not structurally_valid(("request_key",))
    assert not structurally_valid(("tenant", "request_key", "attempt_no"))
    assert "request_key" in grade_plan("AAAA", "count")["false_approvals"]
    assert (
        "no_unique_index" in grade_plan("ABCD", "identity_multiset")["false_approvals"]
    )
    assert not grade_plan("AAA", "identity_multiset")["correctly_classified"] == 32


@pytest.mark.parametrize("trace", ["", "AAAAA", "aabc", "AA;C", "X"])
def test_muse_cannot_execute_unrecognized_actions(trace):
    with pytest.raises(ValueError):
        parse_proposal(
            json.dumps({"schedule": trace, "readout": "count", "reason": "case"})
        )


def test_first_observation_keeps_a_failure_and_its_hash(tmp_path):
    target = tmp_path / "out.json"
    bad = publish_observation(
        target, {"status": "unscored"}, "these are not JSON arguments"
    )
    assert bad["status"] == "unscored" and bad["failure_stage"] == "parse_response"
    assert bad["sha256"] == digest({k: v for k, v in bad.items() if k != "sha256"})
    good = publish_observation(
        target,
        {},
        json.dumps({"schedule": "AAAA", "readout": "count", "reason": "test-only"}),
    )
    assert good["score"]["correctly_classified"] == 23
    assert good["score"]["false_approvals"] and good["status"] == "scored"


def test_frozen_semantics_and_input_hashes_are_intact():
    output = json.loads((ROOT / "docs/intent-semantic-controls.json").read_text())
    g = output["grades"]
    assert output["sha256"] == digest(
        {k: v for k, v in output.items() if k != "sha256"}
    )
    assert [
        (g[name]["matched"], g[name]["pairs_both"])
        for name in ("recorded_muse", "frozen_nli", "nearest_seven")
    ] == [(12, 6), (11, 5), (7, 1)]
    assert [
        op for op, row in g["frozen_nli"]["rows"].items() if not row["correct"]
    ] == ["op_r2b6"]


def test_first_call_is_reused_and_never_resampled(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import openai
    from stateproof import intent_muse as trial

    (tmp_path / "docs").mkdir()
    target = tmp_path / "docs/intent-muse.json"
    empty = json.dumps({"schema": trial.SCHEMA, "status": "not_run"})
    target.write_text(empty)
    (tmp_path / "INTENT_STUDY_PROTOCOL.md").write_bytes(
        (ROOT / "INTENT_STUDY_PROTOCOL.md").read_bytes()
    )
    requests = []

    def respond(**kwargs):
        requests.append(kwargs)
        assert kwargs["input"] == trial.MESSAGE and "AABC" not in kwargs["input"]
        tool = SimpleNamespace(
            type="function_call",
            name="propose_booking_test",
            arguments=json.dumps(
                {
                    "schedule": "AABC",
                    "readout": "identity_multiset",
                    "reason": "Synthetic test only",
                }
            ),
        )
        return SimpleNamespace(id="resp_TEST_ONLY_FIRST", usage=None, output=[tool])

    def fake_client(**kwargs):
        assert kwargs["max_retries"] == 0
        return SimpleNamespace(responses=SimpleNamespace(create=respond))

    monkeypatch.setattr(trial, "ROOT", tmp_path)
    monkeypatch.setattr(trial, "verify_freeze", lambda: "0" * 40)
    monkeypatch.setenv("MODEL_API_KEY", "unit-test-only")
    monkeypatch.setattr(openai, "OpenAI", fake_client)
    first = trial.run_first()
    assert first["score"]["correctly_classified"] == 32
    assert trial.run_first() == first
    target.write_text(
        empty
    )  # recover persisted first response after a lost public output
    monkeypatch.delenv("MODEL_API_KEY")
    assert trial.run_first() == first
    assert len(requests) == 1
