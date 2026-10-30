"""Offline negative control: no provider calls, no secret data in API responses."""
import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

from stateproof.m26_negative_control import run_negative_control
from stateproof.m25_studio import StudioState, make_handler, _HTML
from stateproof.evidence_gate import gate_verdict, verify_chain
from stateproof.evidence_game import cohort


def test_all_nine_controls_are_rejected_without_model_use():
    for i in range(len(cohort())):
        result = run_negative_control(i)
        assert result['attempted_verdict'] == 'VERIFIED'
        assert result['gate_accepted'] is False
        assert result['gate_supported_status'] in {'FAILED', 'INCONCLUSIVE'}
        assert result['api_usage'] == {'input_tokens': 0, 'output_tokens': 0}
        assert result['model_calls'] == 0
        assert len(result['evidence_receipts']) == 1
        assert result['probe_cost'] == 1
        assert gate_verdict(result['workflow'], result['evidence_receipts']) == result['gate_supported_status']
        assert verify_chain(result['case_id'], result['receipt_chain'])
        serialized = json.dumps(result)
        assert 'true_status' not in serialized
        assert 'variant' not in serialized
        assert 'private_evidence' not in serialized
        assert 'NOT a Muse output' in result['label']


def test_control_rejects_invalid_indices():
    for invalid in (True, -1, 9, '3', None):
        try:
            run_negative_control(invalid)
            assert False, invalid
        except ValueError:
            pass


def test_page_communicates_offline_control_not_model_mistake():
    assert 'Challenge the evidence gate (free)' in _HTML
    assert 'not</strong> a Muse mistake' in _HTML
    assert 'OFFLINE NEGATIVE CONTROL' in _HTML
    assert "$('challenge').disabled=isBusy" in _HTML


def test_http_negative_control_security_and_no_live_debit(tmp_path):
    state = StudioState(live_enabled=True, max_live=1, evidence_dir=tmp_path)
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(state))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f'http://127.0.0.1:{server.server_port}'
        def post(payload, token, path='/api/gate-challenge', source=origin):
            c = HTTPConnection('127.0.0.1', server.server_port, timeout=4)
            c.request('POST', path, body=json.dumps(payload), headers={
                'Content-Type': 'application/json', 'X-CSRF-Token': token, 'Origin': source})
            r = c.getresponse()
            code, data = r.status, json.loads(r.read())
            c.close()
            return code, data
        assert post({'case_index': 3}, 'bad')[0] == 403
        assert post({'case_index': 3}, state.csrf, source='https://evil.invalid')[0] == 403
        assert post({'case_index': 3, 'mode': 'meta'}, state.csrf)[0] == 400
        assert post({'case_index': True}, state.csrf)[0] == 400
        status, data = post({'case_index': 3}, state.csrf)
        assert status == 200
        result = data['control']
        assert result['mode'] == 'offline_negative_control'
        assert result['gate_accepted'] is False
        assert state.remaining_live_calls == 1
        assert list(tmp_path.glob('m26_negative_control_case3_*.json'))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=4)
