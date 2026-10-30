"""M9 checks public export against real synthetic receipts with a fake model client."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stateproof.crashlab import digest, load_contract
from stateproof.crashlab_http import INTENT, run_http_experiment
from stateproof.crashlab_trace_replay import replay_source
from stateproof.crashlab_retry_guard import run_guard_experiment
from stateproof.crashlab_case_study import build_public_summary, build_html

DATA = load_contract(Path(__file__).resolve().parents[1] / 'contracts' / 'support_credit.json')
PLAN = {'operation_id': 'apply_credit', 'phase': 'after_commit_lost_ack', 'hypothesis': 'fault test', 'readback': 'ledger'}

class FakeClient:
    def __init__(self):
        self.responses = self
        self.calls = 0
        self.steps = [
            ('inspect_ledger', {'intent_id': INTENT}),
            ('perform_operation', {'intent_id': INTENT}),
            ('inspect_ledger', {'intent_id': INTENT}),
            ('perform_operation', {'intent_id': INTENT}),
            ('inspect_ledger', {'intent_id': INTENT}),
            ('inspect_ledger', {'intent_id': INTENT}),
            ('report_outcome', {'status': 'FAILED', 'reason': 'duplicate detected'}),
        ]
    def create(self, **kwargs):
        name, args = self.steps[self.calls]
        self.calls += 1
        return SimpleNamespace(
            id=f'fake-{self.calls}',
            output=[SimpleNamespace(type='function_call', name=name, arguments=json.dumps(args), call_id=f'id-{self.calls}')],
            usage=SimpleNamespace(input_tokens=3, output_tokens=4),
        )

@pytest.fixture(scope='module')
def records():
    ep = run_http_experiment(DATA, PLAN, actor='muse', readback_fault='stale_zero_once', client=FakeClient())
    wrapper = {'schema': 'stateproof-crashlab-m7-service-recovery-v1', 'case': 'lost_ack_stale_once',
               'row': {'receipt_sha256': ep['receipt_sha256']}, 'episode': ep}
    cf = replay_source(wrapper, DATA)
    precommit = run_guard_experiment(DATA, {**PLAN, 'phase':'before_commit_timeout'},
                                       mode='hard_stop', actor='readback', readback_fault='normal')
    return wrapper, cf, precommit

def test_verified_export(records):
    public = build_public_summary(*records)
    assert public['observed']['effects'] == 2
    assert public['counterfactual']['effects'] == 1
    assert public['counterfactual']['model_continuation'] == 'NOT_OBSERVED'
    assert public['liveness_tradeoff']['committed_effects'] == 0
    assert public['observed']['final_status'] == 'FAILED'
    assert public['record_type'] != 'NEW_LIVE_MUSE_RESULT'

def test_public_export_does_not_embed_raw_receipts(records):
    public = build_public_summary(*records)
    doc = build_html(public)
    assert 'Guarded prefix replay' in doc
    assert 'NOT_OBSERVED' in doc
    assert 'model_continuation_after_denial' not in doc
    assert 'actual_count_private' not in doc
    assert 'private_simulator' not in doc
    assert 'X-CrashLab-Token' not in doc
    assert 'MODEL_API_KEY' not in doc
    assert 'previous_response_id' not in doc
    assert 'synthetic' in doc.lower()

def test_tampered_m7_rejected(records):
    a,b,c = deepcopy(records)
    a['episode']['private_oracle']['effect_count'] = 99
    with pytest.raises(ValueError, match='digest mismatch'):
        build_public_summary(a,b,c)

def test_wrong_m8b_linkage_rejected(records):
    a,b,c = deepcopy(records)
    b['original_m7_receipt_sha256'] = '0' * 64
    b['receipt_sha256'] = digest({k:v for k,v in b.items() if k != 'receipt_sha256'})
    with pytest.raises(ValueError, match='does not link'):
        build_public_summary(a,b,c)

def test_model_continuation_cannot_be_fabricated(records):
    a,b,c = deepcopy(records)
    b['model_continuation_after_denial'] = 'DONE'
    b['receipt_sha256'] = digest({k:v for k,v in b.items() if k != 'receipt_sha256'})
    with pytest.raises(ValueError, match='does not link'):
        build_public_summary(a,b,c)

def test_precommit_tradeoff_required(records):
    a,b,c = deepcopy(records)
    c['oracle']['effect_count'] = 1
    c['receipt_sha256'] = digest({k:v for k,v in c.items() if k != 'receipt_sha256'})
    with pytest.raises(ValueError, match='Expected post-hoc'):
        build_public_summary(a,b,c)

def test_output_html_escapes_script_breakout(records):
    public = build_public_summary(*records)
    public['limitations'].append('</script><script>alert(1)</script>')
    doc = build_html(public)
    assert '</script><script>alert(1)</script>' not in doc
    assert r'\u003c/script\u003e' in doc
