"""Bounded mutation experiment on the identity of state-changing agent operations."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack, closing, contextmanager, nullcontext
import gzip
import hashlib
from itertools import combinations, product
import json
from pathlib import Path
import sqlite3
import uuid

from stateproof.crashlab import digest

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("tenant", "local_intent", "request_key", "payload", "attempt_no")
INTENTS = {
    "A": ("north", "1", "k7"),
    "B": ("north", "2", "k9"),
    "C": ("south", "1", "k7"),
    "D": ("south", "2", "k9"),
}
READOUTS = ("count", "identity_set", "identity_multiset")
CAMPAIGNS = {
    "repeat_only": ("AAAA", "count"),
    "four_distinct": ("ABCD", "identity_multiset"),
    "mixed_count": ("AABC", "count"),
    "mixed_set": ("AABC", "identity_set"),
    "mixed_multiset": ("AABC", "identity_multiset"),
}
INDEXES = tuple(
    columns for size in range(len(FIELDS) + 1) for columns in combinations(FIELDS, size)
)


def index_name(columns):
    return "+".join(columns) or "no_unique_index"


def structurally_valid(columns):
    return (
        "tenant" in columns
        and "attempt_no" not in columns
        and ("local_intent" in columns or "request_key" in columns)
    )


def commands(schedule, payloads="0000"):
    if not 1 <= len(schedule) <= 4 or any(label not in INTENTS for label in schedule):
        raise ValueError("Use one through four public action labels A–D")
    if len(payloads) != 4 or any(value not in "01" for value in payloads):
        raise ValueError("Each intent requires a stable binary payload")
    values = dict(zip(INTENTS, payloads))
    attempts = Counter()
    rows = []
    for label in schedule:
        attempts[label] += 1
        rows.append((*INTENTS[label], values[label], attempts[label]))
    return rows


def business_row(command):
    tenant, intent, _, payload, _ = command
    return tenant, intent, payload


def expected_rows(rows):
    return sorted(set(map(business_row, rows)))


def passes(expected, actual, readout):
    if readout == "count":
        return len(expected) == len(actual)
    if readout == "identity_set":
        return set(expected) == set(actual)
    if readout == "identity_multiset":
        return sorted(expected) == sorted(actual)
    raise ValueError("Unknown final-state readout")


@contextmanager
def experiment_databases():
    # Autocommit each append. Observe committed state through a separate connection.
    with ExitStack() as stack:
        handles = []
        for columns in INDEXES:
            address = f"file:stateproof-{uuid.uuid4().hex}?mode=memory&cache=shared"
            writer = stack.enter_context(
                closing(sqlite3.connect(address, uri=True, isolation_level=None))
            )
            observer = stack.enter_context(
                closing(sqlite3.connect(address, uri=True, isolation_level=None))
            )
            writer.execute(
                "CREATE TABLE bookings(tenant TEXT NOT NULL, local_intent TEXT NOT NULL, request_key TEXT NOT NULL, payload TEXT NOT NULL, attempt_no INTEGER NOT NULL)"
            )
            if columns:
                writer.execute(
                    "CREATE UNIQUE INDEX chosen ON bookings(" + ", ".join(columns) + ")"
                )
            handles.append((columns, writer, observer))
        yield handles


def observe(writer, observer, rows):
    writer.execute("DELETE FROM bookings")
    writer.executemany(
        "INSERT INTO bookings VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING", rows
    )
    return observer.execute(
        "SELECT tenant,local_intent,payload FROM bookings ORDER BY tenant,local_intent,payload"
    ).fetchall()


def grade_in(databases, schedule, readout):
    rows = commands(schedule)
    expected = expected_rows(rows)
    details = []
    for columns, writer, observer in databases:
        actual = observe(writer, observer, rows)
        details.append(
            {
                "index": index_name(columns),
                "reference_valid": structurally_valid(columns),
                "approved": passes(expected, actual, readout),
                "actual": actual,
            }
        )
    false_approvals = [
        r["index"] for r in details if r["approved"] and not r["reference_valid"]
    ]
    false_refusals = [
        r["index"] for r in details if not r["approved"] and r["reference_valid"]
    ]
    return {
        "schedule": schedule,
        "readout": readout,
        "writes": len(rows),
        "expected": expected,
        "false_approvals": false_approvals,
        "false_refusals": false_refusals,
        "correctly_classified": len(details)
        - len(false_approvals)
        - len(false_refusals),
        "adapters": details,
    }


def grade_plan(schedule, readout):
    with experiment_databases() as dbs:
        return grade_in(dbs, schedule, readout)


def run(raw=None):
    search = []
    failures = Counter()
    outcome_hash = hashlib.sha256()
    with experiment_databases() as dbs:
        campaigns = {
            name: grade_in(dbs, trace, readout)
            for name, (trace, readout) in CAMPAIGNS.items()
        }
        for length in range(1, 5):
            total = adequate = 0
            for labels in product(INTENTS, repeat=length):
                schedule = "".join(labels)
                for bits in product("01", repeat=4):
                    payloads = "".join(bits)
                    rows = commands(schedule, payloads)
                    expected = expected_rows(rows)
                    matches_every_reference = True
                    observations = []
                    for columns, writer, observer in dbs:
                        actual = observe(writer, observer, rows)
                        approved = passes(expected, actual, "identity_multiset")
                        if not approved:
                            failures[index_name(columns)] += 1
                        if approved != structurally_valid(columns):
                            matches_every_reference = False
                        observations.append(actual)
                    line = (
                        json.dumps(
                            [schedule, payloads, observations], separators=(",", ":")
                        )
                        + "\n"
                    )
                    outcome_hash.update(line.encode())
                    if raw is not None:
                        raw.write(line)
                    total += 1
                    adequate += int(matches_every_reference)
            search.append(
                {
                    "writes": length,
                    "ordered_schedules": 4**length,
                    "schedule_payload_combinations": total,
                    "combinations_classifying_all_32": adequate,
                }
            )
    agreement = all(
        (failures[index_name(c)] == 0) == structurally_valid(c) for c in INDEXES
    )
    report = {
        "schema": "stateproof-intent-identity-v1",
        "sqlite_version": sqlite3.sqlite_version,
        "protocol_sha256": hashlib.sha256(
            (ROOT / "INTENT_STUDY_PROTOCOL.md").read_bytes()
        ).hexdigest(),
        "logical_intents": INTENTS,
        "field_order": FIELDS,
        "adapter_order": [index_name(c) for c in INDEXES],
        "valid_adapters": sum(map(structurally_valid, INDEXES)),
        "adapters": len(INDEXES),
        "reference_agrees_with_exhaustive_state": agreement,
        "counts_of_histories_with_wrong_state": {
            index_name(c): failures[index_name(c)] for c in INDEXES
        },
        "campaigns": campaigns,
        "search": search,
        "trial_count": sum(r["schedule_payload_combinations"] for r in search)
        * len(INDEXES),
        "ordered_outcomes_sha256": outcome_hash.hexdigest(),
    }
    report["sha256"] = digest(report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out", type=Path, help="Write a new summary and every adapter grade"
    )
    p.add_argument(
        "--raw-gz",
        type=Path,
        help="Write the complete ordered SQLite observations, one JSON record per trace and payload vector",
    )
    args = p.parse_args()
    outputs = [x for x in (args.out, args.raw_gz) if x is not None]
    if len(set(outputs)) != len(outputs) or any(x.exists() for x in outputs):
        p.error("Choose distinct, new output paths")
    with (
        gzip.open(args.raw_gz, "xt", encoding="utf8")
        if args.raw_gz
        else nullcontext() as raw
    ):
        report = run(raw)
    if args.out:
        with args.out.open("x", encoding="utf8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(
        json.dumps(
            {
                "adapters": report["adapters"],
                "valid": report["valid_adapters"],
                "trials": report["trial_count"],
                "search": report["search"],
                "correct": {
                    k: v["correctly_classified"] for k, v in report["campaigns"].items()
                },
                "reference_agrees": report["reference_agrees_with_exhaustive_state"],
                "outcome_hash": report["ordered_outcomes_sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
