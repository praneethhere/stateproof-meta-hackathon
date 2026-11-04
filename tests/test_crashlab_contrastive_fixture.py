"""Prospective synthetic minimal pairs; no Meta API, no external network."""
import json
from pathlib import Path
from stateproof.crashlab import load_contract
from stateproof.crashlab_policy import _writes, local_policy
ROOT=Path(__file__).resolve().parents[1]
PATHS=[ROOT/'contracts'/f'contrastive_semantics_{n}.json' for n in ('a','b')]
MAP=ROOT/'contracts/contrastive_pair_map.json'


def test_six_pairs_blind_identifiers_and_no_private_leak():
    meta=json.loads(MAP.read_text())
    assert meta['never_sent_to_muse'] is True
    pairs=meta['pairs']
    assert len(pairs)==6
    safe_ids={p['safe_id'] for p in pairs}; unsafe_ids={p['unsafe_id'] for p in pairs}
    assert not (safe_ids & unsafe_ids)
    ids=set(); fixture_orders=[]; truth={}
    for path in PATHS:
        d=load_contract(path)
        assert len(d['public']['operations'])==7
        assert len(_writes(d))==6
        public=json.dumps(d['public'])
        assert 'private_simulator' not in public
        assert 'safe_id' not in public and 'unsafe_id' not in public
        assert 'protected' not in public and 'unprotected' not in public
        order=[]
        for row in _writes(d):
            op_id=row['id']; assert op_id.startswith('op_') and len(op_id)==7
            assert op_id not in ids
            ids.add(op_id)
            is_safe=d['private_simulator'][op_id]['dedupe']=='request_key'
            truth[op_id]=is_safe
            assert is_safe == (op_id in safe_ids)
            order.append(is_safe)
        fixture_orders.append(order)
    assert ids==safe_ids|unsafe_ids
    assert sum(truth.values())==6
    assert all(any(v) and not all(v) for v in fixture_orders)
    assert fixture_orders[0]!=fixture_orders[1]


def test_controls_are_reported_as_weak_or_oracle_aware():
    for path in PATHS:
        d=load_contract(path)
        reference={i:s['dedupe']=='request_key' for i,s in d['private_simulator'].items()}
        for name in ('conservative','always_retry','naive_keyword','oracle_reference'):
            p=local_policy(d,name)
            assert len(p['policies'])==6
            correct=sum((row['action']=='retry_same_key')==reference[row['operation_id']] for row in p['policies'])
            if name=='oracle_reference': assert correct==6
            else: assert correct<=6
