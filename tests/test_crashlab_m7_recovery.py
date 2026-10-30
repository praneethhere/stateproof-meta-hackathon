"""No external API calls; test checkpoint and interruption behavior."""
import json
from pathlib import Path

import pytest

from stateproof.crashlab import digest
from stateproof.crashlab_m7_recovery import run
from stateproof.crashlab_recovery_eval import freeze

CONTRACT = Path(__file__).resolve().parents[1] / 'contracts' / 'support_credit.json'


def make_result(data, plan, *, actor, guarded, effort, readback_fault):
    oracle = {'effect_count': 1, 'expected_count': 1, 'correct_state': True, 'excess_effects': 0, 'severity': 1}
    raw = {'actor': actor, 'fault': plan['phase'], 'readback_fault': readback_fault,
           'guarded': guarded, 'actor_events': [], 'actor_report': {'status': 'DONE', 'reason': 'test'},
           'private_oracle': oracle, 'false_done': False, 'attempts': 1,
           'model_usage': {'input_tokens': 10, 'output_tokens': 11}}
    raw['receipt_sha256'] = digest(raw)
    return raw


def prepare(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'evidence').mkdir()
    p = tmp_path/'evidence'/'frozen.json'
    freeze(CONTRACT, p)
    return p, tmp_path/'evidence'/'recovery'


def test_validate_only_has_no_side_effects(tmp_path, monkeypatch):
    frozen, folder = prepare(tmp_path, monkeypatch)
    result = run(frozen, folder, check_only=True)
    assert result['status'] == 'READY' and not folder.exists()


def test_live_requires_explicit_consent(tmp_path, monkeypatch):
    frozen, folder = prepare(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='accept-api-cost'):
        run(frozen, folder)


def test_complete_mocked_batch(tmp_path, monkeypatch):
    frozen, folder = prepare(tmp_path, monkeypatch)
    result = run(frozen, folder, accept_api_cost=True, execute=make_result)
    assert result['status'] == 'COMPLETE' and result['completed'] == 6
    assert len(list(folder.glob('??_*.json'))) == 6
    assert result['rows'][0]['case'] == 'healthy_control'
    with pytest.raises(FileExistsError):
        run(frozen, folder, accept_api_cost=True, execute=make_result)
    again = run(frozen, folder, accept_api_cost=True, resume=True, execute=lambda *a,**k: 1/0)
    assert again['status'] == 'COMPLETE'


def test_incomplete_saves_checkpoint_and_resume_skips_completed(tmp_path, monkeypatch):
    frozen, folder = prepare(tmp_path, monkeypatch)
    counter = {'n': 0}
    def flaky(*args, **kwargs):
        counter['n'] += 1
        if counter['n'] == 3:
            raise RuntimeError('persistence error: SECRET-DO-NOT-PRINT')
        return make_result(*args, **kwargs)
    with pytest.raises(RuntimeError, match='2 completed'):
        run(frozen, folder, accept_api_cost=True, execute=flaky)
    status = run(frozen, folder, check_only=True)
    assert status['completed'] == 2 and status['status'] == 'PARTIAL'
    assert 'SECRET-DO-NOT-PRINT' not in (folder/'events.jsonl').read_text()
    resumed_calls = {'n': 0}
    def resume_func(*args, **kwargs):
        resumed_calls['n'] += 1
        return make_result(*args, **kwargs)
    status = run(frozen, folder, accept_api_cost=True, resume=True, execute=resume_func)
    assert status['completed'] == 6 and resumed_calls['n'] == 4
    assert len(list(folder.glob('error_*.json'))) == 1
    assert status['evidence_type'].startswith('FOLLOW_UP_')


def test_completed_receipt_tamper_rejected(tmp_path, monkeypatch):
    frozen, folder = prepare(tmp_path, monkeypatch)
    run(frozen, folder, accept_api_cost=True, execute=make_result)
    target = folder/'01_healthy_control.json'
    obj = json.loads(target.read_text())
    obj['episode']['private_oracle']['effect_count'] = 900
    target.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match='digest mismatch'):
        run(frozen, folder, check_only=True)


def test_path_guard(tmp_path, monkeypatch):
    frozen, folder = prepare(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='under ./evidence'):
        run(frozen, tmp_path/'badpath', check_only=True)


def test_error_diagnostic_classifies_without_leaking_content():
    from stateproof.crashlab_m7_recovery import _AuditedResponses, _safe_error
    class FakeBadRequest(Exception):
        status_code = 400
        request_id = 'req_123'
        body = {'error': {'type': 'invalid_request_error', 'code': None,
                          'param': 'previous_response_id',
                          'message': 'previous_response_id not found for SECRET-X'}}
    class FakeEndpoint:
        def create(self, **kwargs):
            raise FakeBadRequest('SECRET-X')
    endpoint = _AuditedResponses(FakeEndpoint())
    with pytest.raises(FakeBadRequest) as exc:
        endpoint.create(input=[{'type': 'function_call_output'}], previous_response_id='resp-secret')
    safe = _safe_error(exc.value)
    assert safe['http_status'] == 400
    assert safe['api_error_category'] == 'response_history_reference'
    assert safe['uses_previous_response_id'] is True
    assert safe['api_request_number_in_episode'] == 1
    assert safe['api_error_param'] == 'previous_response_id'
    assert 'SECRET-X' not in str(safe)
    assert 'resp-secret' not in str(safe)


def test_error_diagnostic_tool_call_structure():
    from stateproof.crashlab_m7_recovery import _api_error_category
    assert _api_error_category({'error': {'message': 'unmatched function_call_output call_id'}}) == 'tool_call_history_structure'
    assert _api_error_category({'error': {'message': 'invalid max_output_tokens'}}) == 'token_or_context_budget'
    assert _api_error_category({'error': {'message': 'unrecognized problem'}}) == 'unspecified_400'
