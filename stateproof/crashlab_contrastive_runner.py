"""Two predeclared, single-attempt Meta contrastive contract evaluation runs.

This wrapper binds each live result to the NEW contrastive protocol instead of
reusing the earlier 7-operation experiment's protocol hash. No success editing.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from stateproof.crashlab import digest,load_contract
from stateproof.crashlab_policy import render_html, run


def main():
    p=argparse.ArgumentParser(description='Prospective synthetic contrastive Muse policy challenge')
    p.add_argument('--fixture',choices=('a','b'),required=True)
    p.add_argument('--live',action='store_true')
    p.add_argument('--accept-api-cost',action='store_true')
    p.add_argument('--effort',choices=('medium','high','max'),default='high')
    args=p.parse_args()
    if not (args.live and args.accept_api_cost):
        p.error('A Meta API call requires both --live and --accept-api-cost')
    if not os.environ.get('MODEL_API_KEY'):
        p.error('Set MODEL_API_KEY in this shell before starting a recorded attempt.')
    if args.effort!='high':
        p.error('Protocol requires high effort; do not silently deviate')
    root=Path('.')
    proto=root/'CONTRASTIVE_POLICY_PROTOCOL.md'
    f=root/'contracts'/f'contrastive_semantics_{args.fixture}.json'
    private=root/'evidence'/f'contrast_{args.fixture}_muse.json'
    public=root/'docs'/f'contrast-{args.fixture}-evidence.json'
    page=root/'docs'/f'contrast-{args.fixture}.html'
    if not proto.is_file() or not f.is_file() or any(x.exists() for x in (private,public,page)):
        p.error('Protocol/fixture missing or existing receipt would be overwritten')
    addendum = root / 'CONTRASTIVE_CONTROL_ADDENDUM.md'
    tracked = [str(proto), str(addendum), 'contracts/contrastive_pair_map.json', 'contracts/contrastive_semantics_a.json',
               'contracts/contrastive_semantics_b.json', 'stateproof/crashlab.py', 'stateproof/crashlab_policy.py',
               'stateproof/crashlab_contrastive_runner.py', 'stateproof/crashlab_contrastive_summary.py']
    head = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if (subprocess.run(['git','ls-files','--error-unmatch','--',*tracked],stdout=subprocess.DEVNULL).returncode or
            subprocess.run(['git','diff','--quiet','HEAD','--',*tracked]).returncode or
            subprocess.run(['git','merge-base','--is-ancestor',head,'origin/main']).returncode):
        p.error('Commit your exact experiment and push it to origin/main before calling Muse.')
    data=load_contract(f)
    private.parent.mkdir(parents=True, exist_ok=True)
    attempt = private.with_suffix('.attempt')
    try:
        with attempt.open('x', encoding='utf8') as handle:
            handle.write(datetime.now(timezone.utc).isoformat() + '\n' + head + '\n')
    except FileExistsError:
        p.error(f'An attempt is already recorded in {attempt}. Check earlier outputs and the error journal before any disclosed service retry.')
    try:
        result=run(data,strategy='muse',effort=args.effort)
    except Exception as exc:
        log=root/'evidence'/'contrast_api_errors.jsonl'
        log.parent.mkdir(parents=True,exist_ok=True)
        entry={'created_utc':datetime.now(timezone.utc).isoformat(),'event':'MODEL_RUN_NOT_SCORED',
               'fixture':args.fixture,'status_code':getattr(exc,'status_code',None),
               'error_class':type(exc).__name__,'public_sha256':digest(data['public'])}
        with log.open('a',encoding='utf8') as o: o.write(json.dumps(entry)+'\n')
        print('Meta response not scored. Only bounded diagnostics recorded. Error:',type(exc).__name__)
        raise
    assert result['evidence_type']=='LIVE_META_MODEL_API_RESULT'
    result['prospective_protocol_sha256']=hashlib.sha256(proto.read_bytes()).hexdigest()
    result['comparison_addendum_sha256']=hashlib.sha256(addendum.read_bytes()).hexdigest()
    result['contrastive_fixture']=f.name
    result['git_commit_at_run']=head
    result['receipt_sha256']=digest({k:v for k,v in result.items() if k!='receipt_sha256'})
    for path,content in ((private,json.dumps(result,indent=2)+'\n'),
                         (public,json.dumps(result,indent=2)+'\n'),
                         (page,render_html(result,data))):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content,encoding='utf8')
    print(json.dumps({'fixture':args.fixture,'model_response_id':result['meta']['response_id'],
                      'policy_accuracy':result['evaluation']['policy_accuracy'],
                      'scores':result['evaluation']['scores'],'receipt_sha256':result['receipt_sha256']},indent=2))

if __name__=='__main__':main()
