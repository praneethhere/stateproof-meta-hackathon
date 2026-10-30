"""M8B: validate a counterfactual prefix replay without contacting Meta."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from stateproof.crashlab import digest, load_contract
from stateproof.crashlab_http import INTENT, run_http_experiment
from stateproof.crashlab_trace_replay import replay_source, verify_source

DATA = load_contract(Path(__file__).resolve().parents[1] / 'contracts' / 'support_credit.json')
PLAN = {'operation_id':'apply_credit', 'phase':'after_commit_lost_ack',
        'hypothesis':'test the original risky operation', 'readback':'ledger'}

class FakeClient:
    def __init__(self):
        self.responses = self
        self.calls = 0
        self.steps = [
            ('inspect_ledger', {'intent_id':INTENT}),
            ('perform_operation', {'intent_id':INTENT}),
            ('inspect_ledger', {'intent_id':INTENT}),
            ('perform_operation', {'intent_id':INTENT}),
            ('inspect_ledger', {'intent_id':INTENT}),
            ('inspect_ledger', {'intent_id':INTENT}),
            ('report_outcome', {'status':'FAILED', 'reason':'duplicate effect'})]
    def create(self, **kwargs):
        name, args = self.steps[self.calls]
        self.calls += 1
        return SimpleNamespace(id=f'fake-{self.calls}', output=[SimpleNamespace(type='function_call',
                name=name, arguments=json.dumps(args), call_id=f'f-{self.calls}')],
                usage=SimpleNamespace(input_tokens=12, output_tokens=13))

@pytest.fixture
def source():
    ep = run_http_experiment(DATA, PLAN, actor='muse', readback_fault='stale_zero_once', client=FakeClient())
    assert ep['private_oracle']['effect_count'] == 2
    assert ep['actor_report']['status'] == 'FAILED'
    return {'schema': 'stateproof-crashlab-m7-service-recovery-v1',
            'case':'lost_ack_stale_once', 'row':{'receipt_sha256':ep['receipt_sha256']},
            'episode':ep}

def test_exact_source_prefix_is_accepted(source):
    assert verify_source(source, DATA)['private_oracle']['effect_count'] == 2

def test_replay_stops_at_denied_write_before_second_commit(source):
    out = replay_source(source, DATA)
    assert out['original_m7_outcome'] == {'external_commits': 2, 'final_agent_status':'FAILED'}
    assert out['counterfactual_http_attempts'] == 1
    assert out['counterfactual_effects'] == 1
    assert out['blocked_retry_count'] == 1
    assert out['new_model_calls'] == 0
    assert out['model_continuation_after_denial'] == 'NOT_OBSERVED'
    assert len(out['replay']) == 4 and out['replay'][-1]['divergence_point']
    assert out['replay'][-1]['response']['error'] == 'RETRY_NOT_AUTHORIZED'
    assert out['private_readback_evidence'][1]['actual_count_private'] == 1
    assert out['private_readback_evidence'][1]['observed_count'] == 0
    assert out['receipt_sha256'] == digest({k: v for k, v in out.items() if k != 'receipt_sha256'})

def test_tampered_episode_hash_rejected(source):
    bad = deepcopy(source)
    bad['episode']['private_oracle']['effect_count'] = 100
    with pytest.raises(ValueError, match='receipt hash'):
        replay_source(bad, DATA)

def test_wrong_checkpoint_reference_rejected(source):
    bad = deepcopy(source)
    bad['row']['receipt_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='does not reference'):
        replay_source(bad, DATA)

def test_wrong_tool_prefix_rejected(source):
    bad = deepcopy(source)
    bad['episode']['actor_events'][0]['tool'] = 'perform_operation'
    bad['episode']['receipt_sha256'] = digest({k: v for k, v in bad['episode'].items() if k != 'receipt_sha256'})
    bad['row']['receipt_sha256'] = bad['episode']['receipt_sha256']
    with pytest.raises(ValueError, match='tool sequence'):
        replay_source(bad, DATA)

def test_different_public_contract_rejected(source):
    bad_data = deepcopy(DATA)
    bad_data['public']['task'] = 'Some other task'
    with pytest.raises(ValueError, match='Not the expected'):
        replay_source(source, bad_data)

def test_readback_truth_not_in_actor_replay(source):
    out = replay_source(source, DATA)
    assert out['replay'][2]['response'] == {'ok':True, 'effect_count': 0}
    assert 'actual_count_private' not in json.dumps(out['replay'])


def test_existing_healthy_source_cannot_be_used(source):
    bad = deepcopy(source)
    bad['episode']['private_oracle']['effect_count'] = 1
    bad['episode']['private_oracle']['correct_state'] = True
    bad['episode']['receipt_sha256'] = digest({k:v for k,v in bad['episode'].items() if k != 'receipt_sha256'})
    bad['row']['receipt_sha256'] = bad['episode']['receipt_sha256']
    with pytest.raises(ValueError, match='did not exhibit'):
        replay_source(bad, DATA)
