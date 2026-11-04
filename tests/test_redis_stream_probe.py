import hashlib
import json
import os
from pathlib import Path

import pytest
from stateproof.redis_stream_probe import run

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'plain': 2, 'explicit': 1, 'producer': 2, 'auto': 1, 'auto_content': 2, 'explicit_content': 1}


def assert_stream_observations(record):
    assert {row['id']: row['entry_count'] for row in record['cases']} == EXPECTED
    for row in record['cases']:
        assert row['observed_before_retry'] == 1
        assert row['entry_count'] == len({entry['stream_id'] for entry in row['entries']})
        assert {entry['fields']['shipment'] for entry in row['entries']} == {'shipment-1042'}
        assert row['retry_reply'] in {entry['stream_id'] for entry in row['entries']}


def test_saved_external_observations():
    record = json.loads((ROOT / 'docs/redis-stream-evidence.json').read_text())
    checksum = record.pop('sha256')
    assert checksum == hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert_stream_observations(record)


@pytest.mark.skipif(not os.environ.get('STATEPROOF_REDIS_SERVER'), reason='optional real Redis 8.6+ binary')
def test_actual_redis_stream_appends():
    assert_stream_observations(run(os.environ['STATEPROOF_REDIS_SERVER']))
