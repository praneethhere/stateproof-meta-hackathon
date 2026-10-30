"""M6 offline validation with real loopback M5 episodes and a fake (clearly test-only) model."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stateproof.crashlab import digest, load_contract
from stateproof.crashlab_http import INTENT, run_http_experiment
from stateproof.crashlab_live_showcase import build_public_record, render_html, _receipt

CONTRACT = Path(__file__).resolve().parents[1] / "contracts/support_credit.json"
PLAN = {"operation_id": "apply_credit", "phase": "after_commit_lost_ack",
        "hypothesis": "After-commit response loss can cause duplicate effects",
        "readback": "Look for one effect in the ledger"}

class FakeClient:
    def __init__(self):
        self.responses = self
        self.i = 0
        self.decisions = [("perform_operation", {"intent_id": INTENT}),
                          ("inspect_ledger", {"intent_id": INTENT}),
                          ("report_outcome", {"status": "DONE", "reason": "One credit verified"})]
    def create(self, **req):
        name, arguments = self.decisions[self.i]
        self.i += 1
        return SimpleNamespace(id=f"fake-{self.i}", output=[SimpleNamespace(
            type="function_call", name=name, arguments=json.dumps(arguments), call_id=f"call-{self.i}")],
            usage=SimpleNamespace(input_tokens=7, output_tokens=5))

@pytest.fixture(scope="module")
def receipts(tmp_path_factory):
    base = tmp_path_factory.mktemp("live_showcase")
    data = load_contract(CONTRACT)
    combos = {"blind_retry": ("retry", False, None),
              "readback_first": ("readback", False, None),
              "guarded_retry": ("retry", True, None),
              "muse_actor": ("muse", False, FakeClient())}
    result = {}
    for role, (actor, guarded, client) in combos.items():
        receipt = run_http_experiment(data, PLAN, actor=actor, guarded=guarded, client=client)
        path = base / f"{role}.json"
        path.write_text(json.dumps(receipt))
        result[role] = path
    return result


def test_actual_local_http_evidence(receipts):
    rec = build_public_record(receipts)
    rows = rec["observations"]
    assert [rows[k]["effect_count"] for k in ("blind_retry", "readback_first", "guarded_retry", "muse_actor")] == [2, 1, 1, 1]
    assert rows["blind_retry"]["false_done"] is True
    assert rows["muse_actor"]["false_done"] is False
    assert rows["muse_actor"]["actor"] == "muse"
    assert rec["record_sha256"] == digest({k: v for k, v in rec.items() if k != "record_sha256"})


def test_sanitized_report_contains_no_credentials_or_private_contract(receipts):
    record = build_public_record(receipts)
    src = json.dumps(record)
    assert "private_simulator" not in src
    assert "X-CrashLab-Token" not in src
    assert "SYNTHETIC-REQUEST-001" not in src
    assert "api_key" not in src
    assert "model" not in record["observations"]["blind_retry"]


def test_static_report_renders_actual_roles_without_network(receipts):
    html = render_html(build_public_record(receipts))
    assert "Meta Muse Spark 1.3" in html
    assert "The API said nothing" in html
    assert "fetch(" not in html and "XMLHttpRequest" not in html
    assert "muse_actor" in html and "blind_retry" in html


def test_role_mismatch_rejected(receipts):
    wrong = dict(receipts)
    wrong["blind_retry"] = receipts["guarded_retry"]
    with pytest.raises(ValueError, match="Wrong M5 experiment role"):
        build_public_record(wrong)


def test_tampered_receipt_rejected(receipts, tmp_path):
    orig = json.loads(receipts["blind_retry"].read_text())
    orig["private_oracle"]["effect_count"] = 1
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(orig))
    paths = dict(receipts, blind_retry=bad)
    with pytest.raises(ValueError, match="Receipt changed"):
        build_public_record(paths)


def test_signed_but_inconsistent_oracle_rejected(receipts, tmp_path):
    orig = json.loads(receipts["blind_retry"].read_text())
    orig["private_oracle"]["effect_count"] = 1
    orig["receipt_sha256"] = digest({k: v for k, v in orig.items() if k != "receipt_sha256"})
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(orig))
    with pytest.raises(ValueError, match="Commit events disagree"):
        build_public_record(dict(receipts, blind_retry=bad))


def test_javascript_escape_from_untrusted_reason(receipts, tmp_path):
    bad_reason = '</script><script>alert(1)</script>'
    orig = json.loads(receipts["muse_actor"].read_text())
    orig["actor_report"]["reason"] = bad_reason
    orig["receipt_sha256"] = digest({k: v for k, v in orig.items() if k != "receipt_sha256"})
    path = tmp_path / "valid_modified.json"
    path.write_text(json.dumps(orig))
    html = render_html(build_public_record(dict(receipts, muse_actor=path)))
    assert '<script>alert(1)</script>' not in html
    assert '\u003c' in html


def test_missing_or_extra_roles_fail(receipts):
    bad = {k: v for k, v in receipts.items() if k != "muse_actor"}
    with pytest.raises(ValueError, match="exactly these four"):
        build_public_record(bad)


def test_mixed_contract_rejected(receipts, tmp_path):
    orig = json.loads(receipts["muse_actor"].read_text())
    orig["public_contract_sha256"] = "other-contract"
    orig["receipt_sha256"] = digest({k: v for k, v in orig.items() if k != "receipt_sha256"})
    path = tmp_path / "different.json"
    path.write_text(json.dumps(orig))
    with pytest.raises(ValueError, match="same operation and public contract"):
        build_public_record(dict(receipts, muse_actor=path))
