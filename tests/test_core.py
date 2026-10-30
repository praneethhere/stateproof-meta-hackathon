from stateproof.core import run_case


def test_retry_without_idempotency_is_a_false_success():
    outcome = run_case(enforce_idempotency=False)
    assert outcome["simulated_agent"]["reported_status"] == "success"
    assert outcome["verification"]["verified"] is False
    assert outcome["verification"]["observed_charge_count"] == 2
    assert outcome["verification"]["observed_total_cents"] == 5000


def test_idempotency_survives_lost_response():
    outcome = run_case(enforce_idempotency=True)
    assert outcome["simulated_agent"]["reported_status"] == "success"
    assert outcome["verification"]["verified"] is True
    assert outcome["verification"]["observed_charge_count"] == 1
    assert outcome["verification"]["observed_total_cents"] == 2500


def test_initial_attempt_has_lost_response_in_both_cases():
    for enabled in (False, True):
        trace = run_case(enforce_idempotency=enabled)["simulated_agent"]["attempts"]
        assert len(trace) == 2
        assert trace[0]["observation"] == "timeout_after_commit_unknown_to_client"
        assert trace[1]["observation"] == "success"
