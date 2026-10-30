"""M4 read-only HTML report. All tests are synthetic and offline."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stateproof.crashlab_eval import freeze_cases, evaluate
from stateproof.crashlab_showcase import (
    prepare_showcase, render_showcase, export_showcase,
)


class FakeClient:
    def __init__(self):
        self.responses = self

    def create(self, **kwargs):
        # Intentionally choose the second operation on both held-out fixtures.
        return SimpleNamespace(output=[SimpleNamespace(
            type="function_call", name="submit_crash_plan", arguments=json.dumps({
                "operation_id": "write_b", "phase": "after_commit_lost_ack",
                "hypothesis": "Check if retries duplicate a committed write",
                "readback": "Verify ledger reflects one effect",
            }))], usage=SimpleNamespace(input_tokens=123, output_tokens=456))


def make_evidence(tmp_path):
    contract_files = []
    for name, configurations in [
        ("alpha", ("request_key", "none")),
        ("beta", ("none", "request_key")),
    ]:
        data = {
            "public": {
                "scenario": name,
                "task": "Complete one write",
                "operations": [
                    {"id": "write_a", "method": "POST", "description": "Record one action"},
                    {"id": "write_b", "method": "POST", "description": "Record another action"},
                ],
            },
            "private_simulator": {
                "write_a": {"dedupe": configurations[0], "severity": 2},
                "write_b": {"dedupe": configurations[1], "severity": 5},
            },
            "private_note": "DO_NOT_LEAK_PRIVATE_NOTE_9KK3",
        }
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(data))
        contract_files.append(path)
    freeze_path = tmp_path / "frozen_manifest.json"
    freeze_cases(contract_files, freeze_path)
    live_result = evaluate(freeze_path, live=True, client=FakeClient())
    live_path = tmp_path / "live_results.json"
    live_path.write_text(json.dumps(live_result))
    return freeze_path, live_path


def test_preparation_verifies_replays(tmp_path):
    freeze, live = make_evidence(tmp_path)
    report = prepare_showcase(freeze, live)
    assert len(report["rows"]) == 8
    assert report["integrity"]["contracts_reverified"] is True
    assert report["integrity"]["replays_reverified"] is True
    alpha = next(r for r in report["rows"] if r["case"] == "alpha" and r["strategy"] == "muse")
    assert alpha["false_success"]
    assert len(alpha["replayed_events"]) == 2
    assert alpha["observed_effect_count"] == 2


def test_report_never_exports_private_simulator_data(tmp_path):
    freeze, live = make_evidence(tmp_path)
    output = tmp_path / "safe.html"
    receipt = export_showcase(freeze, live, output)
    text = output.read_text()
    assert receipt["external_api_calls"] == 0
    assert receipt["private_simulator_exported"] is False
    assert "DO_NOT_LEAK_PRIVATE_NOTE_9KK3" not in text
    assert '"private_simulator"' not in text
    assert "\\u003c" not in text or '<script>alert(1)</script>' not in text
    assert "Muse Spark 1.3" in text
    assert "RE-EXECUTED" in text


def test_prevents_script_breakout(tmp_path):
    freeze, live = make_evidence(tmp_path)
    obj = prepare_showcase(freeze, live)
    obj["rows"][0]["hypothesis"] = '</script><script>alert(1)</script>'
    page = render_showcase(obj)
    assert '</script><script>alert(1)</script>' not in page
    assert "\\u003c/script\\u003e" in page


def test_rejects_tampered_receipt_or_oracle(tmp_path):
    freeze, live = make_evidence(tmp_path)
    obj = json.loads(live.read_text())
    obj["rows"][0]["observed_effect_count"] = 999
    live.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="Replay disagrees"):
        prepare_showcase(freeze, live)


def test_rejects_forged_summary(tmp_path):
    freeze, live = make_evidence(tmp_path)
    obj = json.loads(live.read_text())
    obj["summary"]["muse"]["confirmed_exposures"] += 1
    live.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="summary disagrees"):
        prepare_showcase(freeze, live)


def test_rejects_frozen_contract_edit(tmp_path):
    freeze, live = make_evidence(tmp_path)
    (tmp_path / "alpha.json").write_text((tmp_path / "alpha.json").read_text() + " ")
    with pytest.raises(ValueError, match="changed"):
        prepare_showcase(freeze, live)


def test_no_silent_report_overwrite(tmp_path):
    freeze, live = make_evidence(tmp_path)
    output = tmp_path / "report.html"
    export_showcase(freeze, live, output)
    with pytest.raises(FileExistsError):
        export_showcase(freeze, live, output)


def test_rejects_non_live_result(tmp_path):
    freeze, live = make_evidence(tmp_path)
    obj = json.loads(live.read_text())
    obj["mode"] = "offline_baselines_only"
    live.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="live Muse"):
        prepare_showcase(freeze, live)
