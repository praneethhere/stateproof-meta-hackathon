"""Reproduce a StateProof booking retry in SQLite. Run this file with Python 3."""
import json
import re
import sqlite3
import unittest
from contextlib import closing

# The browser export replaces only the following assignment with your selected case.
CASE = {"index_sql": "CREATE UNIQUE INDEX retry_key ON reservations(request_key, attempt_no)", "fault": "after", "key": "forward", "policy": "retry_same_key"}  # EXPORTED_CASE

CREATE_TABLE = "CREATE TABLE reservations (id INTEGER PRIMARY KEY, intent_id TEXT NOT NULL, request_key TEXT, attempt_no INTEGER NOT NULL)"
INSERT = "INSERT INTO reservations(intent_id, request_key, attempt_no) VALUES (?, ?, ?) ON CONFLICT DO NOTHING"
READ = "SELECT id, intent_id, request_key, attempt_no FROM reservations ORDER BY id"
INTENT = "BOOK-1042"
REQUEST_KEY = "req-1042"
COLUMN = r"(?:request_key|intent_id|attempt_no)"
INDEX_PATTERN = rf"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+[a-z_][a-z0-9_]*\s+ON\s+reservations\s*\(\s*{COLUMN}(?:\s*,\s*{COLUMN}){{0,2}}\s*\)\s*;?\s*$"


def database(index_sql):
    if len(index_sql) > 300 or re.fullmatch(INDEX_PATTERN, index_sql, re.I | re.ASCII) is None:
        raise ValueError('Enter one CREATE [UNIQUE] INDEX on request_key, intent_id or attempt_no.')
    db = sqlite3.connect(':memory:', isolation_level=None)
    try:
        db.execute(CREATE_TABLE)
        db.execute(index_sql)
    except Exception:
        db.close()
        raise
    return db


def attempt(db, case, number):
    key = REQUEST_KEY if case['key'] == 'forward' else None
    db.execute(INSERT, (INTENT, key, number))


def probe(case):
    with closing(database(case['index_sql'])) as disposable:
        attempt(disposable, case, 1)
        attempt(disposable, case, 2)
        return len(disposable.execute(READ).fetchall())


def run_case(case, verify):
    if case['fault'] not in ('before', 'after') or case['key'] not in ('forward', 'drop') or case['policy'] not in ('retry_same_key', 'verify_then_escalate'):
        raise ValueError('Unsupported fault, key binding or policy')
    permitted = case['policy'] == 'retry_same_key'
    if verify and permitted:
        permitted = probe(case) == 1
    with closing(database(case['index_sql'])) as db:
        if case['fault'] == 'after':
            attempt(db, case, 1)
        # The caller receives no acknowledgement under either injected fault.
        if permitted:
            attempt(db, case, 2)
        return db.execute(READ).fetchall()


class BookingRetryRegression(unittest.TestCase):
    def assert_one_booking(self, verify):
        rows = run_case(CASE, verify)
        self.assertEqual(len(rows), 1, f'Expected 1 reservation for {INTENT}; SQLite returned {len(rows)}. Rows: {rows}')

    def test_recorded_policy(self):
        self.assert_one_booking(verify=False)

    def test_policy_with_probe(self):
        self.assert_one_booking(verify=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
