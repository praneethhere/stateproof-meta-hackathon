"""All test Muse receipts here are intentionally synthetic; no live model is called."""
import copy
import json
from pathlib import Path

import pytest

from stateproof.crashlab import digest, load_contract
from stateproof.crashlab_policy import local_policy
from stateproof.crashlab_contract_audit import audit, render_html, validate_record

DATA = load_contract(Path(__file__).resolve().parents[1] / 'contracts/policy_challenges.json')


def fake_saved_muse_policy():
    policy = local_policy(DATA, 'oracle_reference')
    for row in policy['policies']:
        row['reason'] = 'TEST FIXTURE: not an actual Meta-generated policy'
    receipt = {
        'schema': 'stateproof-crashlab-policy-eval-v1',
        'evidence_type': 'LIVE_META_MODEL_API_RESULT',  # test-only stand-in for saved-record parser
        'strategy': 'muse', 'public_contract_sha256': digest(DATA['public']),
        'policy': policy,
        'meta': {'model': 'muse-spark-1.3', 'response_id': 'resp_TEST_FIXTURE_NOT_LIVE'},
    }
    receipt['receipt_sha256'] = digest(receipt)
    return receipt


def test_rejects_tampered_or_mismatched_receipts():
    rec = fake_saved_muse_policy()
    validate_record(DATA, rec)
    bad = copy.deepcopy(rec)
    bad['policy']['policies'][0]['action'] = 'verify_then_escalate'
    with pytest.raises(ValueError, match='checksum'):
        validate_record(DATA, bad)
    bad = copy.deepcopy(rec)
    bad['public_contract_sha256'] = 'forged'
    bad['receipt_sha256'] = digest({k: v for k, v in bad.items() if k != 'receipt_sha256'})
    with pytest.raises(ValueError, match='different public contract'):
        validate_record(DATA, bad)
    bad = copy.deepcopy(rec)
    bad['evidence_type'] = 'DETERMINISTIC_OFFLINE_REFERENCE_NOT_META'
    bad['receipt_sha256'] = digest({k: v for k, v in bad.items() if k != 'receipt_sha256'})
    with pytest.raises(ValueError, match='live Meta'):
        validate_record(DATA, bad)


def test_synthetic_drift_audit_flags_actual_sqlite_contradiction_and_blocks_unsafe_reissue():
    result = audit(DATA, fake_saved_muse_policy())
    assert result['evidence_type'] == 'RECORDED_MUSE_POLICY_PLUS_DETERMINISTIC_SYNTHETIC_DRIFT_AUDIT'
    assert result['score']['operations'] == 7
    assert result['score']['scenarios'] == 14
    assert result['score']['critical_mismatches'] == 1
    assert result['score']['conservative_mismatches'] == 1
    assert result['score']['duplicates_after_boundary'] == 0
    by_id = {r['operation_id']: r for r in result['operations']}
    assert by_id['reserve_slot']['probe_independent_sqlite_effects'] == 2
    assert by_id['reserve_slot']['status'] == 'CRITICAL_CONTRACT_MISMATCH'
    assert not by_id['reserve_slot']['synthetic_retry_authorized']
    assert by_id['charge_freight']['probe_independent_sqlite_effects'] == 1
    assert by_id['charge_freight']['status'] == 'CONSERVATIVE_CONTRACT_MISMATCH'
    assert not by_id['charge_freight']['synthetic_retry_authorized']
    lost = [r for r in result['trials'] if r['operation_id'] == 'reserve_slot' and r['fault'] == 'after_commit_lost_ack']
    assert len(lost) == 1
    assert lost[0]['oracle_effects'] == 1
    assert lost[0]['denied_writes'] == 1
    assert result['receipt_sha256'] == digest({k: v for k, v in result.items() if k != 'receipt_sha256'})
    html = render_html(result)
    assert 'What if the API contract' in html
    assert 'RECORDED MUSE POLICY' in html
    assert 'POST-HOC' not in html or 'post-hoc' in html.lower()
    assert 'model_policy_response_id' not in html
    assert 'resp_TEST_FIXTURE_NOT_LIVE' in html
    assert '2 SQLite effects' in html
    assert '<button data-index="1"' in html


def test_no_drift_has_no_mismatches_and_seven_operations():
    result = audit(DATA, fake_saved_muse_policy(), drift={})
    assert result['score']['critical_mismatches'] == 0
    assert result['score']['conservative_mismatches'] == 0
    assert result['score']['duplicates_after_boundary'] == 0


def test_rejects_unknown_drift_op_or_behavior():
    r = fake_saved_muse_policy()
    with pytest.raises(ValueError):
        audit(DATA, r, drift={'production_url': 'none'})
    with pytest.raises(ValueError):
        audit(DATA, r, drift={'reserve_slot': 'unknown'})


def test_separate_saved_live_muse_receipt_is_bounded_and_cannot_fake_continuation():
    from stateproof.crashlab_contract_audit import sanitize_live_guard
    fake_m8 = {
        'schema': 'stateproof-crashlab-m8-retry-boundary-v1',
        'actor': 'muse', 'mode': 'hard_stop',
        'fault': 'after_commit_lost_ack', 'readback_fault': 'stale_zero_once',
        'guarded_server': False,
        'oracle': {'effect_count': 1, 'correct_state': True},
        'actor_report': {'status': 'DONE', 'reason': 'test fixture'},
        'denied_writes': 1, 'external_write_attempts': 1, 'actor_requested_writes': 2,
        'model_usage': {'input_tokens': 0, 'output_tokens': 0},
        'actor_events': [
            {'turn': 1, 'tool': 'perform_operation', 'accepted': True,
             'observation': {'ok': False, 'error': 'TIMEOUT_OUTCOME_UNKNOWN', 'secret': 'DO_NOT_EXPORT'}},
            {'turn': 2, 'tool': 'inspect_ledger', 'accepted': True,
             'observation': {'ok': True, 'effect_count': 1}},
            {'turn': 3, 'tool': 'report_outcome', 'accepted': True, 'observation': {'ok': True}},
        ],
    }
    fake_m8['receipt_sha256'] = digest(fake_m8)
    summary = sanitize_live_guard(fake_m8)
    assert summary['oracle_effect_count'] == 1
    assert summary['evidence_type'].startswith('SEPARATE_SAVED_LIVE_MUSE')
    assert 'DO_NOT_EXPORT' not in json.dumps(summary)
    report = audit(DATA, fake_saved_muse_policy())
    report['separate_live_guard_episode'] = summary
    view = render_html(report)
    assert 'Muse continued after the boundary refused' in view
    assert 'SEPARATE_SAVED_LIVE_MUSE' not in view or 'Separately' in view
    tampered = copy.deepcopy(fake_m8)
    tampered['oracle']['effect_count'] = 2
    with pytest.raises(ValueError, match='checksum'):
        sanitize_live_guard(tampered)
    tampered = copy.deepcopy(fake_m8)
    tampered['actor_report']['status'] = 'FAILED'
    tampered['receipt_sha256'] = digest({k: v for k, v in tampered.items() if k != 'receipt_sha256'})
    with pytest.raises(ValueError, match='does not match'):
        sanitize_live_guard(tampered)
