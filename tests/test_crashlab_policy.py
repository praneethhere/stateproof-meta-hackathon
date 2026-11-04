"""Offline tests only: no Meta API, no external network, and no real customer data."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stateproof.crashlab import digest, load_contract
from stateproof.crashlab_policy import (
    evaluate_policy, local_policy, muse_policy, render_html, run, validate_policy
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/policy_challenges.json"


def data():
    return load_contract(CONTRACT)


class FakeClient:
    def __init__(self, response):
        self.responses = self
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_response(policy):
    return SimpleNamespace(
        id="resp-test-01",
        output=[SimpleNamespace(type="function_call", name="submit_retry_policy",
                                arguments=json.dumps(policy))],
        usage=SimpleNamespace(input_tokens=140, output_tokens=210),
    )


def test_8_operation_fixture_is_valid_and_excludes_readonly():
    d = data()
    assert len(d["public"]["operations"]) == 8
    assert len(local_policy(d, "conservative")["policies"]) == 7
    assert "view_status" not in str(local_policy(d, "conservative"))


def test_offline_control_scores_are_reproducible():
    d = data()
    for name in ("conservative", "naive_keyword", "always_retry", "oracle_reference"):
        x = evaluate_policy(d, local_policy(d, name))
        y = evaluate_policy(d, local_policy(d, name))
        assert x == y
        assert x["scores"]["scenarios"] == 14
        assert x["scores"]["duplicates"] == 0  # trusted adapter fails closed
        assert all(r["committed_effects"] <= 1 for r in x["rows"])
        assert all(r["attempted_http_writes"] <= 2 for r in x["rows"])


def test_oracle_reference_success_and_safety_vs_conservative_liveness_cost():
    d = data()
    upper = evaluate_policy(d, local_policy(d, "oracle_reference"))
    hard = evaluate_policy(d, local_policy(d, "conservative"))
    assert upper["policy_accuracy"] == {"matched": 7, "total": 7}
    assert upper["scores"]["completed_correctly"] > hard["scores"]["completed_correctly"]
    assert upper["scores"]["duplicates"] == 0
    assert hard["scores"]["duplicates"] == 0
    assert any(r["committed_effects"] == 0 and r["fault"] == "before_commit_timeout"
               for r in hard["rows"])


def test_model_does_not_override_verified_adapter_and_trusted_gate_rejects_bad_policy():
    d = data()
    all_retry = evaluate_policy(d, local_policy(d, "always_retry"))
    assert all_retry["scores"]["duplicates"] == 0
    assert all_retry["scores"]["policy_overrides"] > 0
    assert any(r["model_claim_rejected_by_trusted_adapter"] for r in all_retry["rows"])


def test_frozen_policy_validation_rejects_missing_duplicate_and_fake_quotes():
    d = data()
    good = local_policy(d, "conservative")
    validate_policy(good, d)
    with pytest.raises(ValueError, match="cover every"):
        validate_policy({"policies": good["policies"][:-1]}, d)
    bad = json.loads(json.dumps(good))
    bad["policies"][1]["operation_id"] = bad["policies"][0]["operation_id"]
    with pytest.raises(ValueError, match="duplicate"):
        validate_policy(bad, d)
    bad = json.loads(json.dumps(good))
    bad["policies"][0]["quote"] = "provider guarantees safe exactly once forever"
    with pytest.raises(ValueError, match="quote"):
        validate_policy(bad, d)
    bad = json.loads(json.dumps(good))
    bad["policies"][0]["action"] = "run_shell_script"
    with pytest.raises(ValueError, match="Unsupported"):
        validate_policy(bad, d)
    bad = json.loads(json.dumps(good))
    bad["policies"].append({"operation_id": "view_status", "action": "retry_same_key",
                             "quote": "Read-only", "reason": "read only"})
    with pytest.raises(ValueError):
        validate_policy(bad, d)


def test_fake_muse_receipt_and_request_never_leak_private_simulator():
    d = data()
    policy = local_policy(d, "oracle_reference")  # fake output, not actually Meta-generated
    fake = FakeClient(fake_response(policy))
    result, metadata = muse_policy(d, client=fake)
    assert result == policy
    assert metadata["response_id"] == "resp-test-01"
    assert metadata["input_tokens"] == 140
    request = json.dumps(fake.calls)
    assert "private_simulator" not in request
    assert "charge_freight\": {\"dedupe\"" not in request
    assert "MODEL_API_KEY" not in request
    assert "submit_retry_policy" in request
    assert "reasoning" in request
    assert "max_output_tokens" in request


def test_muse_policy_bad_tool_call_is_not_silently_scored():
    d = data()
    fake = FakeClient(SimpleNamespace(id="r", output=[], usage=None))
    with pytest.raises(RuntimeError, match="Exactly one"):
        muse_policy(d, client=fake)


def test_fake_model_run_is_labelled_as_not_a_real_model_call():
    d = data()
    fake = FakeClient(fake_response(local_policy(d, "conservative")))
    result = run(d, strategy="muse", client=fake)
    assert result["evidence_type"] == "INJECTED_FAKE_MODEL_TEST_NOT_LIVE"
    assert result["receipt_sha256"] == digest({k: v for k, v in result.items() if k != "receipt_sha256"})
    assert result["evaluation"]["scores"]["scenarios"] == 14
    assert "deterministic_readback_first" in result["methodology"]["actor"]


def test_html_is_source_checked_and_escapes_untrusted_model_text():
    d = data()
    p = local_policy(d, "conservative")
    p["policies"][0]["reason"] = '<script>window.evil=true</script>'
    fake = FakeClient(fake_response(p))
    result = run(d, strategy="muse", client=fake)
    html = render_html(result, d)
    assert "&lt;script&gt;window.evil=true&lt;/script&gt;" in html
    assert '<script>window.evil=true</script>' not in html
    assert "RECORDED META MODEL API RESPONSE" in html
    assert "deterministic client" in html
    assert result["receipt_sha256"] in html


def test_no_hidden_private_truth_in_policy_return():
    d = data()
    fake = FakeClient(fake_response(local_policy(d, "conservative")))
    policy, _ = muse_policy(d, client=fake)
    assert "private_simulator" not in json.dumps(policy)
    assert "server_has_verified_deduplication" not in json.dumps(policy)


def test_output_no_over_claim_model_superiority():
    d = data()
    result = run(d, strategy="conservative")
    html = render_html(result, d)
    assert "DETERMINISTIC OFFLINE CONTROL" in html
    assert "No new retry protocol" in html
    assert result["meta"]["response_id"] is None
