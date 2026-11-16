#!/usr/bin/env python3
"""Read-only SQLite sensitivity check for StateProof's AABC intent study.

Run from the StateProof repository root:
    python3 ~/Downloads/stateproof_retry_identity_sensitivity.py

All mutations are performed in temporary, in-memory SQLite databases.
The reference expected state remains the ORIGINAL three business intents
(A, B, C), making the interpretation explicit: subsequent A is a retry,
not an approved change to the intent. Passing here does not establish
correct error handling for a conflicting payload: it may be silently ignored.
"""
from __future__ import annotations

import sys
from pathlib import Path

root = Path.cwd()
if not (root / "stateproof/intent_study.py").is_file():
    raise SystemExit("STOP: run this script from the StateProof repository root")
sys.path.insert(0, str(root))
from stateproof import intent_study as study

base = study.commands("AABC")
assert base[0][0:3] == base[1][0:3], "Unexpected AABC trace shape"
expected = study.expected_rows(base)  # one each of A, B, C

cases = [
    ("stable key + stable payload", False, False, 6),
    ("fresh key on retry", True, False, 2),
    ("changed payload on retry", False, True, 3),
    ("fresh key + changed payload", True, True, 1),
]

print("Original expected intents:", expected)
print("Readout: exact multiset of (tenant, local_intent, payload)\n")
with study.experiment_databases() as dbs:
    for label, rotate_key, change_payload, expected_passes in cases:
        rows = list(base)
        retry = list(rows[1])  # the second A, not the initial write
        if rotate_key:
            retry[2] = "k7-fresh"
        if change_payload:
            retry[3] = "1"
        rows[1] = tuple(retry)

        still_pass = []
        false_pass = []
        outcomes = set()
        for columns, writer, observer in dbs:
            actual = study.observe(writer, observer, rows)
            outcomes.add(tuple(actual))
            accepted = study.passes(expected, actual, "identity_multiset")
            name = study.index_name(columns)
            if study.structurally_valid(columns):
                if accepted:
                    still_pass.append(name)
            elif accepted:
                false_pass.append(name)

        print(label)
        print(f"  originally valid configurations passing: {len(still_pass)}/6")
        print(f"  configurations: {', '.join(still_pass) or '(none)'}")
        print(f"  originally invalid configurations passing: {len(false_pass)}/26")
        print(f"  observed final-state patterns: {len(outcomes)}")
        assert len(still_pass) == expected_passes, "Unexpected result: investigate"
        assert not false_pass, "Unexpected false acceptance: investigate"

print("\nPASS: bounded retry-metadata sensitivity replicated")
print("INTERPRETATION: Changed payload requires a separately specified conflict policy.")
print("These are synthetic SQLite cases, not observed agent retries.")
