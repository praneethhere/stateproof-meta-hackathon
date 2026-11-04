"""Synthetic offline stand-ins ONLY; no model calls or actual Meta identity."""
import copy
import json
import hashlib
from pathlib import Path

import pytest
from stateproof.crashlab import digest,load_contract
from stateproof.crashlab_policy import run
from stateproof.crashlab_contrastive_summary import compile_report,render_html

BASE=Path(__file__).resolve().parents[1]
PATHS=[BASE/'contracts'/f'contrastive_semantics_{x}.json' for x in ('a','b')]


def fake_saved_receipts(tmp_path):
    saved=[]
    for name,path in zip(('a','b'),PATHS):
        # A deterministic oracle-aware policy is NOT a model baseline. It only
        # exercises the public receipt parser in this unit test.
        result=run(load_contract(path),strategy='oracle_reference')
        result['strategy']='muse'
        result['evidence_type']='LIVE_META_MODEL_API_RESULT'  # Test-only synthetic stand-in
        result['meta']={'model':'muse-spark-1.3','response_id':'resp_TEST_ONLY_'+name}
        result['prospective_protocol_sha256']=hashlib.sha256((BASE/'CONTRASTIVE_POLICY_PROTOCOL.md').read_bytes()).hexdigest()
        result['contrastive_fixture']=path.name
        result['receipt_sha256']=digest({k:v for k,v in result.items() if k!='receipt_sha256'})
        target=tmp_path/(name+'.json')
        target.write_text(json.dumps(result))
        saved.append(target)
    return saved


def test_contrastive_summary_checks_every_prediction_and_reports_weak_baselines(tmp_path):
    recs=fake_saved_receipts(tmp_path)
    report=compile_report(PATHS,recs,BASE/'CONTRASTIVE_POLICY_PROTOCOL.md')
    assert report['score']['operations']==12
    assert report['score']['policy_correct']==12
    assert report['score']['pairs_both_correct']==6
    assert report['score']['scenarios']==24
    assert report['score']['duplicates']==0
    assert len(report['operations'])==12
    assert all(x<=12 for x in report['weak_baseline_classification'].values())
    assert report['weak_baseline_classification']['negation_keyword']==6
    assert set(report['baseline_complete_pairs'].values())=={0}
    assert not report['extra_control_frozen_before_model_calls']
    assert len(report['sources'])==2
    assert report['receipt_sha256']==digest({k:v for k,v in report.items() if k!='receipt_sha256'})
    page=render_html(report)
    assert 'word that flips the rule' in page
    assert '12/12' in page
    assert 'TWO RECORDED MODEL CALLS' in page
    assert 'This is' in page


def test_summary_rejects_receipt_tampering_and_faked_reused_model_call(tmp_path):
    recs=fake_saved_receipts(tmp_path)
    text=json.loads(recs[0].read_text())
    text['evaluation']['policy_accuracy']['matched']=0
    recs[0].write_text(json.dumps(text))
    with pytest.raises(ValueError,match='checksum'):
        compile_report(PATHS,recs,BASE/'CONTRASTIVE_POLICY_PROTOCOL.md')
    recs=fake_saved_receipts(tmp_path)
    a=json.loads(recs[0].read_text())
    b=json.loads(recs[1].read_text())
    b['meta']['response_id']=a['meta']['response_id']
    b['receipt_sha256']=digest({k:v for k,v in b.items() if k!='receipt_sha256'})
    recs[1].write_text(json.dumps(b))
    with pytest.raises(ValueError,match='distinct'):
        compile_report(PATHS,recs,BASE/'CONTRASTIVE_POLICY_PROTOCOL.md')
