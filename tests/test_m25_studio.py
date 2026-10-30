"""M2.5 local studio tests (offline only; no network or Meta credit usage)."""
import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from pathlib import Path
from stateproof.m25_studio import StudioState, make_handler, public_cases, run_studio_case


def request(server, method, path, payload=None, csrf=None, origin=None):
    conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
    headers = {}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        headers['X-CSRF-Token'] = csrf or ''
        if origin is not None:
            headers['Origin'] = origin
        payload = json.dumps(payload)
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    body = response.read()
    code = response.status
    conn.close()
    return code, body


def start_server(state):
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(state))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_public_cases_hide_private_outcomes():
    c = public_cases()
    assert len(c) == 9
    assert 'variant' not in json.dumps(c)
    assert 'true_status' not in json.dumps(c)
    assert 'private_evidence' not in json.dumps(c)
    assert any(x['workflow'] == 'rollout' for x in c)


def test_offline_studio_case_includes_clear_baseline_disclosure():
    result = run_studio_case(3, 'offline')
    assert result['receipt']['mode'] == 'offline'
    assert result['receipt']['gate_supported_status'] in ('VERIFIED', 'FAILED', 'INCONCLUSIVE')
    assert result['receipt']['api_usage'] == {'input_tokens': 0, 'output_tokens': 0}
    assert set(result['baselines']) == {'contract_aware', 'cheap_first', 'random'}
    assert 'not a blind benchmark' in result['comparison_warning']


def test_invalid_case_and_modes_are_rejected():
    for index, mode in [(9,'offline'), (-1,'offline'), (True,'offline'), (0,'danger'), (0,'META')]:
        try:
            run_studio_case(index, mode)
            assert False, (index, mode)
        except ValueError:
            pass


def test_studio_http_security_and_offline_mode(tmp_path):
    state = StudioState(live_enabled=False, max_live=0, evidence_dir=tmp_path)
    server, thread = start_server(state)
    try:
        code, body = request(server, 'GET', '/')
        assert code == 200
        assert b'Agent said success' in body
        assert b'private evaluator truth' in body
        code, body = request(server, 'GET', '/api/cases')
        assert code == 200
        v = json.loads(body)
        assert v['live_enabled'] is False and v['remaining_live_calls'] == 0
        assert 'variant' not in body.decode()
        path = '/api/run'
        payload = {'case_index': 3, 'mode': 'offline'}
        origin = f'http://127.0.0.1:{server.server_port}'
        assert request(server, 'POST', path, payload, 'wrong', origin)[0] == 403
        assert request(server, 'POST', path, payload, state.csrf, 'https://evil.example')[0] == 403
        assert request(server, 'POST', path, {'case_index': 3, 'mode': 'meta'}, state.csrf, origin)[0] == 403
        assert request(server, 'POST', path, {'case_index': True, 'mode': 'offline'}, state.csrf, origin)[0] == 400
        assert request(server, 'POST', path, {'case_index': 3, 'mode': 'offline', 'extra': 1}, state.csrf, origin)[0] == 400
        code, body = request(server, 'POST', path, payload, state.csrf, origin)
        assert code == 200, body
        result = json.loads(body)
        assert result['receipt']['mode'] == 'offline'
        assert result['receipt']['api_usage']['input_tokens'] == 0
        assert len(list(tmp_path.glob('m25_offline_case3_*.json'))) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_http_root_no_api_calls_by_default():
    state = StudioState(live_enabled=False, max_live=0)
    server, thread = start_server(state)
    try:
        for path in ('/', '/?utm_source=chatgpt.com', '/index.html?utm_source=chatgpt.com', '/api/cases', '/api/cases?utm_source=chatgpt.com', '/'):
            assert request(server, 'GET', path)[0] == 200
        assert state.remaining_live_calls == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
