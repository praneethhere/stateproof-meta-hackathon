import json
from pathlib import Path

import pytest
from stateproof import booking_regression as booking
from stateproof.build_retry_lab import ROOT, browser_data, javascript

STABLE = 'CREATE UNIQUE INDEX retry_key ON reservations(request_key)'
LOOKUP = 'CREATE INDEX retry_key ON reservations(request_key)'


@pytest.mark.parametrize('index_sql,key,fault,expected', [
    (booking.CASE['index_sql'], 'forward', 'after', (2, 1)),
    (STABLE, 'forward', 'after', (1, 1)),
    (STABLE, 'drop', 'after', (2, 1)),
    (LOOKUP, 'forward', 'before', (1, 0)),
    (STABLE, 'forward', 'before', (1, 1)),
])
def test_rehearsal_counts_actual_rows(index_sql, key, fault, expected):
    case = {**booking.CASE, 'index_sql': index_sql, 'key': key, 'fault': fault}
    assert tuple(len(booking.run_case(case, verify)) for verify in (False, True)) == expected


def test_harness_exports_only_one_index_and_tracks_its_source():
    with pytest.raises(ValueError):
        booking.database(STABLE + '; DROP TABLE reservations')
    generated = browser_data()
    assert generated['policy']['action'] == 'retry_same_key'
    assert generated['policy']['quote'] in generated['description']
    assert (ROOT / 'docs/retry-lab-data.js').read_text() == javascript()
