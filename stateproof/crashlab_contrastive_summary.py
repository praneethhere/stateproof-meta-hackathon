"""Check and summarize two prospective, synthetic recorded Muse policy receipts.

This exporter makes no model calls. No result is accepted without recorded
Meta evidence and the full scored operation rows. No selection by performance.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import html
import json
import re

from stateproof.crashlab import digest,load_contract
from stateproof.crashlab_policy import local_policy,validate_policy,_writes

STRATEGIES=('conservative','always_retry','naive_keyword','negation_keyword')
NEGATED_DEDUP = re.compile(r'\b(?:no|not|without)\s+(?:\w+\s+){0,2}dedup\w*\b', re.I)


def control_grades(data, strategy):
    base = 'naive_keyword' if strategy == 'negation_keyword' else strategy
    descriptions = {op['id']: op['description'] for op in _writes(data)}
    grades = {}
    for row in local_policy(data, base)['policies']:
        op = row['operation_id']
        allow = row['action'] == 'retry_same_key'
        if strategy == 'negation_keyword' and NEGATED_DEDUP.search(descriptions[op]):
            allow = False
        grades[op] = allow == (data['private_simulator'][op]['dedupe'] == 'request_key')
    return grades


def compile_report(contract_paths: list[Path], receipt_paths: list[Path], protocol_path: Path,
                   pair_map_path: Path | None = None) -> dict:
    if len(contract_paths)!=2 or len(receipt_paths)!=2:
        raise ValueError('Exactly two predeclared fixtures and two recorded receipts required')
    if not protocol_path.is_file():
        raise ValueError('Prospective protocol file missing')
    pair_map_path = pair_map_path or (contract_paths[0].parent / 'contrastive_pair_map.json')
    pair_map = json.loads(pair_map_path.read_text(encoding='utf8'))
    if pair_map.get('schema') != 'stateproof-contrastive-pair-manifest-v1' or pair_map.get('never_sent_to_muse') is not True:
        raise ValueError('Missing independently held pair manifest')
    operations=[]; sample_refs=[]; calls=[]
    controls={name:{} for name in STRATEGIES}
    protocol_hash = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    addendum_hash = hashlib.sha256((protocol_path.parent / 'CONTRASTIVE_CONTROL_ADDENDUM.md').read_bytes()).hexdigest()
    frozen_addendum = True
    scores={'policy_correct':0,'operations':0,'correct_final_state':0,'scenarios':0,
            'duplicates':0,'incomplete':0}
    for path,receipt_path in zip(contract_paths,receipt_paths):
        data=load_contract(path)
        receipt=json.loads(receipt_path.read_text(encoding='utf8'))
        if receipt.get('evidence_type')!='LIVE_META_MODEL_API_RESULT' or receipt.get('strategy')!='muse':
            raise ValueError('Only successful recorded Muse policy evidence is accepted')
        if receipt.get('meta',{}).get('model')!='muse-spark-1.3' or not str(receipt.get('meta',{}).get('response_id','')).startswith('resp_'):
            raise ValueError('Muse response identity missing')
        if receipt.get('public_contract_sha256') != digest(data['public']):
            raise ValueError('Fixture and recorded policy do not match')
        if receipt.get('receipt_sha256')!=digest({k:v for k,v in receipt.items() if k!='receipt_sha256'}):
            raise ValueError('Receipt checksum mismatch')
        if receipt.get('prospective_protocol_sha256') != protocol_hash or receipt.get('contrastive_fixture') != path.name:
            raise ValueError('Receipt points to a different protocol or fixture')
        frozen_addendum = frozen_addendum and receipt.get('comparison_addendum_sha256') == addendum_hash
        validate_policy(receipt['policy'],data)
        corrects=receipt.get('evaluation',{}).get('classifications',[])
        if len(corrects)!=len(_writes(data)):
            raise ValueError('Incomplete operation scores')
        by_op={x['operation_id']:x for x in corrects}
        published={p['operation_id']:p for p in receipt['policy']['policies']}
        for op in _writes(data):
            name=op['id']
            spec=data['private_simulator'][name]
            truth=spec['dedupe']=='request_key'
            model=published[name]
            expected='retry_same_key' if truth else 'verify_then_escalate'
            if by_op.get(name,{}).get('action')!=model['action'] or by_op.get(name,{}).get('policy_matches_reference') is not (model['action']==expected):
                raise ValueError('Inconsistent saved classification')
            operations.append({'operation_id':name,'reference':expected,'muse_action':model['action'],
                               'muse_quote':model['quote'],'correct':model['action']==expected})
        fixture_accuracy=sum(v['correct'] for v in operations[-len(_writes(data)):])
        if receipt['evaluation'].get('policy_accuracy')!={'matched':fixture_accuracy,'total':len(_writes(data))}:
            raise ValueError('Saved accuracy does not match operation rows')
        e=receipt['evaluation']['scores']
        rows = receipt['evaluation']['rows']
        conditions = {(op['id'], fault) for op in _writes(data) for fault in ('before_commit_timeout','after_commit_lost_ack')}
        if len(rows) != len(conditions) or {(r['operation_id'],r['fault']) for r in rows} != conditions:
            raise ValueError('Missing or repeated fault condition')
        counts = [r['committed_effects'] for r in rows]
        if (e['scenarios'] != len(counts) or e['completed_correctly'] != counts.count(1) or
                e['incomplete'] != len(counts) - counts.count(1) or e['duplicates'] != sum(n > 1 for n in counts)):
            raise ValueError('Invalid scenario counts')
        scores['operations']+=len(_writes(data));scores['policy_correct']+=fixture_accuracy
        scores['scenarios']+=e['scenarios'];scores['correct_final_state']+=e['completed_correctly']
        scores['duplicates']+=e['duplicates'];scores['incomplete']+=e['incomplete']
        sample_refs.append({'fixture':path.name,'response_id':receipt['meta']['response_id'],
                            'receipt_sha256':receipt['receipt_sha256'],'git_commit_at_run':receipt.get('git_commit_at_run')})
        for name in STRATEGIES:
            controls[name].update(control_grades(data, name))
        calls.append(receipt['meta']['response_id'])
    if len(set(calls))!=2:
        raise ValueError('Two distinct model responses expected')
    lookup={op['operation_id']:op for op in operations}
    pair_meta=pair_map.get('pairs',[])
    if not isinstance(pair_meta,list) or len(pair_meta)!=6:
        raise ValueError('Six paired manifest entries required')
    pair_ids=set()
    pairs=[]
    for entry in pair_meta:
        safe=entry['safe_id']; unsafe=entry['unsafe_id']; name=entry['name']
        if safe not in lookup or unsafe not in lookup or safe==unsafe or safe in pair_ids or unsafe in pair_ids:
            raise ValueError('Pair manifest missing, duplicated or invalid')
        pair_ids.update((safe,unsafe))
        if lookup[safe]['reference']!='retry_same_key' or lookup[unsafe]['reference']!='verify_then_escalate':
            raise ValueError('Pair manifest contradicts private scored references')
        lookup[safe]['pair_name']=name
        lookup[unsafe]['pair_name']=name
        pairs.append((lookup[safe],lookup[unsafe]))
    if pair_ids!=set(lookup):
        raise ValueError('Pair manifest fails to cover every operation')
    pairs_correct=sum(all(x['correct'] for x in pair) for pair in pairs)
    report={'schema':'stateproof-crashlab-contrastive-summary-v1',
            'created_utc':datetime.now(timezone.utc).isoformat(),
            'evidence_type':'TWO_RECORDED_META_RESPONSES_PLUS_DETERMINISTIC_SYNTHETIC_SCORING',
            'experiment':'six_author_designed_synthetic_minimal_pairs_two_precommitted_batches',
            'protocol_sha256':hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
            'pair_map_sha256':hashlib.sha256(pair_map_path.read_bytes()).hexdigest(),
            'score':{**scores,'pairs_both_correct':pairs_correct,'pairs':6},
            'weak_baseline_classification':{name:sum(grades.values()) for name, grades in controls.items()},
            'baseline_complete_pairs':{name:sum(grades[p['safe_id']] and grades[p['unsafe_id']] for p in pair_meta) for name, grades in controls.items()},
            'extra_control_frozen_before_model_calls': frozen_addendum,
            'sources':sample_refs,'operations':operations,
            'limitations':[
                'Two model responses total, one per hand-authored fixture; not a model population performance estimate.',
                'Minimal pairs and reference labels were constructed by the same project team.',
                'Keyword heuristic is intentionally simplistic; neither it nor conservative/always-retry is a strong language baseline.',
                'A trusted adapter protects HTTP execution; correct final state is NOT evidence of Muse-alone safety.',
                'The underlying fault scenarios use a deterministic actor, not live Muse tool execution.',
                'No claim of novelty or superiority to a frontier-model baseline is supported.',
            ]}
    report['receipt_sha256']=digest(report)
    return report


def render_html(report:dict)->str:
    e=lambda x: html.escape(str(x),quote=True)
    s=report['score']
    baselines=report['weak_baseline_classification']
    comparison=''.join(f'<tr><td>{e(name)}</td><td>{n}/{s["operations"]}</td><td>{report["baseline_complete_pairs"][name]}/{s["pairs"]} full pairs</td></tr>' for name,n in baselines.items())
    timing = 'included in both pre-call receipts' if report['extra_control_frozen_before_model_calls'] else 'retrospective comparison'
    comparison += f'<tr><td colspan="3">The negation rule was fitted to the original seven examples. For this challenge: {timing}.</td></tr>'
    rows=''.join(f'<tr><td><code>{e(row["operation_id"])}</code><br><small>{e(row["pair_name"])}</small></td><td>{e(row["muse_action"])}</td><td><span class="{"ok" if row["correct"] else "bad"}">{"MATCH" if row["correct"] else "MISS"}</span></td><td>{e(row["muse_quote"])}</td></tr>' for row in report['operations'])
    receipts=''.join(f'<p class="mono">{e(r["fixture"])} · {e(r["response_id"])} · {e(r["receipt_sha256"][:16])}…</p>' for r in report['sources'])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>StateProof CrashLab · Contrastive Contract Challenge</title><style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#0a111e;color:#ebf4ff;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1130px;margin:auto;padding:34px 20px}}a{{color:#8ee6d6}}h1{{font-size:clamp(2rem,5vw,3.5rem);line-height:1.1}}.tag{{color:#8ee6d6;font-weight:800;letter-spacing:.12em;font-size:.8rem}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}}.card{{background:#152338;border:1px solid #354968;border-radius:16px;padding:20px;margin:14px 0}}.cards strong{{display:block;font-size:2rem}}.cards small,p{{color:#b9cbe3}}table{{border-collapse:collapse;min-width:720px;width:100%}}th,td{{padding:11px;text-align:left;vertical-align:top;border-bottom:1px solid #354968;font-size:.85rem}}th{{color:#93b6cf}}.scroll{{overflow:auto}}code,.mono{{font:13px ui-monospace,monospace;overflow-wrap:anywhere}}.ok{{color:#93f5bd}}.bad{{color:#ffab92}}.warning{{border-left:4px solid #d7ae68;padding-left:15px}}nav{{display:flex;gap:16px;flex-wrap:wrap}}
</style></head><body><main><nav><a href="./index.html">Crash planner</a><a href="./audit.html">Contract drift</a><a href="./policy.html">First seven-operation policy</a></nav><p class="tag">META MUSE SPARK 1.3 · TWO RECORDED MODEL CALLS</p><h1>Does the agent understand the <em>word that flips the rule?</em></h1><p>Six synthetic minimal pairs differ only in whether a stable key prevents a second side effect. Each saved Meta policy was graded against author-declared references, then a deterministic client executed controlled local HTTP/SQLite faults. This is <b>not</b> a deployed API.</p><section class="cards"><div class="card"><strong>{s['policy_correct']}/{s['operations']}</strong><small>Muse policy classifications</small></div><div class="card"><strong>{s['pairs_both_correct']}/{s['pairs']}</strong><small>Entire minimal pairs correct</small></div><div class="card"><strong>{s['correct_final_state']}/{s['scenarios']}</strong><small>Correct end states with trusted adapter</small></div><div class="card"><strong>{s['duplicates']}</strong><small>Duplicates after deterministic gate</small></div></section><section class="card"><h2>Required controls — show where heuristics stand</h2><div class="scroll"><table><thead><tr><th>Strategy</th><th>Policy classification</th><th>Limitation</th></tr></thead><tbody><tr><td><b>Recorded Muse policies</b></td><td><b>{s['policy_correct']}/{s['operations']}</b></td><td>One output per hand-authored fixture</td></tr>{comparison}</tbody></table></div></section><section class="card"><h2>All original predictions, including any mistakes</h2><div class="scroll"><table><thead><tr><th>Mutation</th><th>Muse recommendation</th><th>Grade</th><th>Exact cited contract text</th></tr></thead><tbody>{rows}</tbody></table></div></section><section class="card warning"><h2>Evidence and limitations</h2><p>Both results came from actual Meta Model API policy responses. The page is a <b>recording</b>, not a live inference endpoint. The test inputs were authored to distinguish negation and guarantee language and do not represent naturally sampled provider docs. A strong deterministic parser or another LLM may perform equally well. The trusted adapter prevents duplicates regardless of incorrect policy recommendations, so do not credit all end-state correctness to Muse.</p>{receipts}<p class="mono">Summary SHA-256: {e(report['receipt_sha256'])}</p><a href="./contrast-evidence.json">Full sanitized summary JSON</a> · <a href="https://github.com/praneethhere/stateproof-meta-hackathon">Source code</a></section></main></body></html>'''


def main():
    p=argparse.ArgumentParser(description='Two source-checked prospective Muse contrastive receipts')
    p.add_argument('--a',type=Path,default=Path('docs/contrast-a-evidence.json'))
    p.add_argument('--b',type=Path,default=Path('docs/contrast-b-evidence.json'))
    p.add_argument('--protocol',type=Path,default=Path('CONTRASTIVE_POLICY_PROTOCOL.md'))
    p.add_argument('--pair-map',type=Path,default=Path('contracts/contrastive_pair_map.json'))
    p.add_argument('--public-out',type=Path,default=Path('docs/contrast-evidence.json'))
    p.add_argument('--html',type=Path,default=Path('docs/contrast.html'))
    args=p.parse_args()
    if args.public_out==args.html or args.public_out.exists() or args.html.exists():
        p.error('Output already exists or overlaps; refuse to overwrite')
    result=compile_report([Path('contracts/contrastive_semantics_a.json'),Path('contracts/contrastive_semantics_b.json')],
                          [args.a,args.b],args.protocol,args.pair_map)
    for path,content in ((args.public_out,json.dumps(result,indent=2)+'\n'),(args.html,render_html(result))):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content,encoding='utf8')
    print(json.dumps({'score':result['score'],'weak_baselines':result['weak_baseline_classification'],
                      'response_ids':[v['response_id'] for v in result['sources']],
                      'receipt_sha256':result['receipt_sha256']},indent=2))
if __name__=='__main__':main()
