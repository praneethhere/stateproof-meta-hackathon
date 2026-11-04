"""Build the offline browser inputs from the saved policy receipt and runnable Python test."""
import json
import hashlib
from pathlib import Path

from stateproof import booking_regression as booking
from stateproof.crashlab import digest

ROOT = Path(__file__).resolve().parents[1]


def browser_data():
    record = json.loads((ROOT / 'docs/policy-evidence.json').read_text())
    contract = json.loads((ROOT / 'contracts/policy_challenges.json').read_text())['public']
    claimed_hash = record['receipt_sha256']
    if claimed_hash != digest({k:v for k,v in record.items() if k != 'receipt_sha256'}) or record['public_contract_sha256'] != digest(contract):
        raise ValueError('Policy receipt or public contract hash mismatch')
    if record['evidence_type'] != 'LIVE_META_MODEL_API_RESULT' or record['meta']['model'] != 'muse-spark-1.3':
        raise ValueError('Expected a recorded Muse Spark 1.3 policy')
    policy = next(row for row in record['policy']['policies'] if row['operation_id'] == 'reserve_slot')
    description = next(row['description'] for row in contract['operations'] if row['id'] == policy['operation_id'])
    if policy['quote'] not in description or policy['action'] != 'retry_same_key':
        raise ValueError('Expected the recorded reservation policy and its exact supporting text')
    source = (ROOT / 'stateproof/booking_regression.py').read_text()
    lines = [line for line in source.splitlines() if line.endswith('# EXPORTED_CASE')]
    if len(lines) != 1:
        raise ValueError('Regression template marker is ambiguous')
    pair_result = None
    summary_file = ROOT / 'docs/contrast-evidence.json'
    if summary_file.exists():
        from stateproof.crashlab_contrastive_summary import compile_report
        stored = json.loads(summary_file.read_text())
        expected = compile_report([ROOT / f'contracts/contrastive_semantics_{name}.json' for name in ('a','b')],
                                  [ROOT / f'docs/contrast-{name}-evidence.json' for name in ('a','b')],
                                  ROOT / 'CONTRASTIVE_POLICY_PROTOCOL.md')
        if (stored.get('receipt_sha256') != digest({k:v for k,v in stored.items() if k != 'receipt_sha256'})
                or stored.get('score') != expected['score'] or stored.get('sources') != expected['sources']):
            raise ValueError('Pair summary does not match both recorded model receipts')
        pair_result = {**expected['score'], 'controls': expected['baseline_complete_pairs'],
                       'example': [op for op in expected['operations'] if op['pair_name'] == 'webhook_deliver']}
    redis = json.loads((ROOT / 'docs/redis-stream-evidence.json').read_text())
    redis_hash = hashlib.sha256(json.dumps({k:v for k,v in redis.items() if k != 'sha256'}, sort_keys=True, separators=(',',':')).encode()).hexdigest()
    if redis_hash != redis['sha256'] or any(len(c['entries']) != c['entry_count'] for c in redis['cases']):
        raise ValueError('Redis receipt does not match its hash or observed stream entries')
    return {'meta': record['meta'], 'receipt': claimed_hash, 'policy': policy, 'description': description, 'pairResult': pair_result, 'redis': redis,
            'table': booking.CREATE_TABLE, 'insert': booking.INSERT, 'read': booking.READ,
            'intent': booking.INTENT, 'key': booking.REQUEST_KEY, 'indexPattern': booking.INDEX_PATTERN,
            'defaultCase': booking.CASE, 'template': source, 'templateLine': lines[0]}


def javascript():
    return 'window.CRASHLAB = ' + json.dumps(browser_data(), indent=2, ensure_ascii=True).replace('</','<\\/') + ';\n'


if __name__ == '__main__':
    (ROOT / 'docs/retry-lab-data.js').write_text(javascript(), encoding='utf-8')
