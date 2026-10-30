import json
from types import SimpleNamespace as N
import pytest
from stateproof.evidence_game import Case, Episode, SPECS, cohort
from stateproof.evidence_gate import gate_verdict, proof_chain, verify_chain
from stateproof.m24_runner import run_offline_gated, run_muse_gated
from stateproof.m24_report import render_html


def test_without_evidence_must_abstain():
    for workflow in ('order', 'rollout', 'refund'):
        assert gate_verdict(workflow, []) == 'INCONCLUSIVE'


def test_shortcuts_cannot_prove_workflow_complete():
    assert gate_verdict('rollout', [{'probe_id': 'ci_status', 'evidence': {'ci_status': 'success'}}]) == 'INCONCLUSIVE'
    assert gate_verdict('order', [{'probe_id': 'charge_count', 'evidence': {'charge_count': 1}}]) == 'INCONCLUSIVE'
    assert gate_verdict('refund', [{'probe_id': 'processor_ack', 'evidence': {'processor_ack': 'accepted'}}]) == 'INCONCLUSIVE'


def test_counterfactual_worlds_remain_indistinguishable_without_readback():
    for variants in [(Case('order', 'good'), Case('order', 'unfulfilled')),
                     (Case('rollout', 'good'), Case('rollout', 'stale')),
                     (Case('refund', 'good'), Case('refund', 'unsettled'))]:
        a, b = [Episode(v, 'same-id') for v in variants]
        try:
            assert a.public_view() == b.public_view()
            assert gate_verdict(a.public_view()['workflow'], a.records) == 'INCONCLUSIVE'
            assert gate_verdict(b.public_view()['workflow'], b.records) == 'INCONCLUSIVE'
        finally:
            a.close(); b.close()


@pytest.mark.parametrize('case', SPECS)
def test_offline_gate_matches_scorer_where_evidence_available(case):
    r = run_offline_gated(case, 'x')
    assert r['gate_accepted']
    assert r['gate_supported_status'] == r['evidence_supported_status']
    assert verify_chain('x', r['receipt_chain'])
    if r['claimed_status'] != 'INCONCLUSIVE':
        assert r['claimed_status'] == r['true_status']


def test_hash_chain_detects_changed_observations():
    chain = proof_chain('x', [{'probe_id': 'x', 'evidence': {'n': 1}}])
    assert verify_chain('x', chain)
    chain[0]['observation']['evidence']['n'] = 2
    assert not verify_chain('x', chain)


def test_invalid_or_unsupported_readbacks_are_inconclusive():
    assert gate_verdict('refund', [{'probe_id': 'settlement_state', 'evidence': {'state': 'UNAVAILABLE'}}]) == 'INCONCLUSIVE'
    assert gate_verdict('rollout', [{'probe_id': 'runtime_revision', 'evidence': {'revision': None}}]) == 'INCONCLUSIVE'
    assert gate_verdict('order', [{'probe_id': 'charge_count', 'evidence': {'charge_count': True}}]) == 'INCONCLUSIVE'


def test_html_renders_and_escapes_untrusted_explanation():
    result = run_offline_gated(Case('rollout', 'stale'), 'example')
    result['model_explanation'] = '<script>alert(1)</script>'
    html = render_html(result)
    assert '&lt;script&gt;' in html
    assert '<script>alert(1)</script>' not in html
    assert 'Hidden outcome' in html
    assert 'FAILED' in html


class FakeClient:
    def __init__(self, steps):
        self.steps = iter(steps)
        self.responses = self
        self.kwargs = []
    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        return next(self.steps)


def call(name, args, ident='c1'):
    return N(type='function_call', name=name, arguments=json.dumps(args), call_id=ident)


def resp(ident, *calls):
    return N(id=ident, output=list(calls), usage=N(input_tokens=10, output_tokens=5))


def test_model_tool_and_gate_good_case():
    client = FakeClient([
        resp('r1', call('inspect_evidence', {'probe_id': 'runtime_revision'})),
        resp('r2', call('submit_verdict', {'verdict': 'VERIFIED', 'explanation': 'Active r2'})),
    ])
    r = run_muse_gated(Case('rollout', 'good'), 'case', client=client)
    assert r['claimed_status'] == 'VERIFIED'
    assert r['gate_accepted'] and r['correct_vs_truth']
    assert r['api_usage']['input_tokens'] == 20
    assert client.kwargs[1]['previous_response_id'] == 'r1'
    assert verify_chain('case', r['receipt_chain'])


def test_model_unsupported_verdict_is_rejected_without_truth_leak():
    client = FakeClient([
        resp('r1', call('submit_verdict', {'verdict': 'VERIFIED', 'explanation': 'Guess'})),
        resp('r2', call('inspect_evidence', {'probe_id': 'runtime_revision'})),
        resp('r3', call('submit_verdict', {'verdict': 'FAILED', 'explanation': 'Observed r1'})),
    ])
    r = run_muse_gated(Case('rollout', 'stale'), 'case', client=client)
    assert r['claimed_status'] == 'FAILED'
    assert r['gate_accepted'] and r['correct_vs_truth']
    assert r['rejected_claims'][0]['requested'] == 'VERIFIED'
    assert r['rejected_claims'][0]['gate_status'] == 'INCONCLUSIVE'
    assert 'true_status' not in json.dumps(client.kwargs)
    assert 'stale' not in json.dumps(client.kwargs)


def test_model_bad_tool_and_no_useful_verdict():
    client = FakeClient([
        resp('r1', call('inspect_evidence', {'probe_id': '../.ssh'})),
        resp('r2', call('submit_verdict', {'verdict': 'INCONCLUSIVE', 'explanation': 'No observations'})),
    ])
    r = run_muse_gated(Case('rollout', 'stale'), 'case', client=client)
    assert r['claimed_status'] == 'INCONCLUSIVE'
    assert not r['correct_vs_truth']
    assert r['tool_calls'][0]['accepted'] is False
    assert r['cost'] == 0


def test_tool_limit_prevents_unbounded_calls():
    client = FakeClient([resp('r1', call('inspect_evidence', {'probe_id': 'ci_status'}))])
    r = run_muse_gated(Case('rollout', 'stale'), 'case', client=client, max_calls=1)
    assert r['termination'] == 'call_limit'
    assert r['cost'] == 1
