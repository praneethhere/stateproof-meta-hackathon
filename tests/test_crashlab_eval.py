"""Offline-only tests; never call Meta's API."""
import copy
from pathlib import Path
import json
from types import SimpleNamespace
import pytest

from stateproof.crashlab_eval import freeze_cases, evaluate, _load_freeze


def contract(path: Path, scenario: str, dedupe_a: str, dedupe_b: str):
    obj = {
        "public": {"scenario": scenario, "task": "Perform operation exactly once", "operations": [
            {"id": "write_a", "method": "POST", "description": "A customer-facing operation"},
            {"id": "write_b", "method": "POST", "description": "A second customer-facing operation"},
        ]},
        "private_simulator": {
            "write_a": {"dedupe": dedupe_a, "severity": 2},
            "write_b": {"dedupe": dedupe_b, "severity": 5},
        },
    }
    path.write_text(json.dumps(obj))
    return path


def setup(tmp_path):
    one = contract(tmp_path / "alpha.json", "Alpha", "request_key", "none")
    two = contract(tmp_path / "beta.json", "Beta", "none", "request_key")
    manifest = tmp_path / "frozen.json"
    return one, two, manifest


def test_freeze_and_run_offline(tmp_path):
    a, b, manifest = setup(tmp_path)
    freeze_cases([a, b], manifest)
    result = evaluate(manifest)
    assert result["mode"] == "offline_baselines_only"
    assert len(result["rows"]) == 6
    assert result["summary"]["writes_first"]["confirmed_exposures"] == 1
    assert "muse" not in result["summary"]
    assert "private_simulator" not in json.dumps(result)


def test_no_overwrite(tmp_path):
    a, b, manifest = setup(tmp_path)
    freeze_cases([a, b], manifest)
    with pytest.raises(FileExistsError):
        freeze_cases([a, b], manifest)


def test_tamper_detected(tmp_path):
    a, b, manifest = setup(tmp_path)
    freeze_cases([a, b], manifest)
    a.write_text(a.read_text() + " ")
    with pytest.raises(ValueError, match="changed"):
        evaluate(manifest)


def test_minimum_two_contracts(tmp_path):
    a, b, manifest = setup(tmp_path)
    with pytest.raises(ValueError, match="2-4"):
        freeze_cases([a], manifest)


def test_schema_lock(tmp_path):
    a, b, manifest = setup(tmp_path)
    freeze_cases([a, b], manifest)
    obj = json.loads(manifest.read_text())
    obj["protocol"]["random_seed"] = 9000
    manifest.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="differs"):
        _load_freeze(manifest)


class FakeClient:
    def __init__(self):
        self.responses = self
        self.prompt_list = []

    def create(self, **kwargs):
        self.prompt_list.append(kwargs["input"])
        return SimpleNamespace(
            output=[SimpleNamespace(type="function_call", name="submit_crash_plan",
                                    arguments=json.dumps({
                                        "operation_id": "write_b", "phase": "after_commit_lost_ack",
                                        "hypothesis": "Test effect duplication", "readback": "ledger count"
                                    }))],
            usage=SimpleNamespace(input_tokens=20, output_tokens=30),
        )


def test_live_mock_does_not_leak_private(tmp_path):
    a, b, manifest = setup(tmp_path)
    freeze_cases([a, b], manifest)
    fake = FakeClient()
    r = evaluate(manifest, live=True, client=fake)
    assert len(fake.prompt_list) == 2
    assert all("private_simulator" not in prompt for prompt in fake.prompt_list)
    assert "muse" in r["summary"]
    assert r["summary"]["muse"]["confirmed_exposures"] == 1


def test_live_no_api_without_flag(tmp_path, monkeypatch):
    # evaluate() with its default live=False cannot call muse_plan.
    a, b, manifest = setup(tmp_path)
    freeze_cases([a, b], manifest)
    def deny(*args, **kwargs):
        raise AssertionError("Never call model in offline mode")
    monkeypatch.setattr("stateproof.crashlab_eval.muse_plan", deny)
    evaluate(manifest)


class WrongPhaseClient(FakeClient):
    def create(self, **kwargs):
        out = super().create(**kwargs)
        out.output[0].arguments = json.dumps({
            "operation_id": "write_b", "phase": "no_fault",
            "hypothesis": "This is not the protocol fault phase", "readback": "ledger count",
        })
        return out


def test_out_of_protocol_muse_plan_is_scored_as_miss_not_executed(tmp_path):
    a, b, manifest = setup(tmp_path)
    freeze_cases([a, b], manifest)
    result = evaluate(manifest, live=True, client=WrongPhaseClient())
    muse_rows = [row for row in result["rows"] if row["strategy"] == "muse"]
    assert len(muse_rows) == 2
    assert all(row["invalid_reason"] == "MODEL_SELECTED_NONFROZEN_FAULT_PHASE" for row in muse_rows)
    assert all(row["observed_effect_count"] is None for row in muse_rows)
    assert result["summary"]["muse"]["invalid_phase_selections"] == 2
    assert result["summary"]["muse"]["confirmed_exposures"] == 0
