"""Secondary checks proposed after the main result. No additional model inference."""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def grouped_behavior(docs):
    summary = json.loads((docs / "intent-study-evidence.json").read_text())
    names = summary["adapter_order"]
    hashes = [hashlib.sha256() for _ in names]
    with gzip.open(docs / "intent-observations.jsonl.gz", "rt") as source:
        for line in source:
            _, _, observations = json.loads(line)
            for fingerprint, rows in zip(hashes, observations, strict=True):
                fingerprint.update(
                    json.dumps(rows, separators=(",", ":")).encode() + b"\n"
                )
    grouped = defaultdict(list)
    for name, fingerprint in zip(names, hashes, strict=True):
        grouped[fingerprint.hexdigest()].append(name)
    class_errors = {}
    for task, result in summary["campaigns"].items():
        invalid_approved = set(result["false_approvals"])
        for group in grouped.values():
            if 0 < len(invalid_approved.intersection(group)) < len(group):
                raise ValueError(
                    "Equivalent adapter choices received conflicting grades"
                )
        class_errors[task] = sum(
            group[0] in invalid_approved for group in grouped.values()
        )
    valid = {
        x for x, k in summary["counts_of_histories_with_wrong_state"].items() if k == 0
    }
    return {
        "equivalent_on": "observed business-row multisets over the complete finite corpus",
        "groups": len(grouped),
        "valid_groups": sum(group[0] in valid for group in grouped.values()),
        "members_by_outcome_fingerprint": dict(grouped),
        "false_approvals_by_group": class_errors,
    }


def out_of_family():
    # This intentionally partial index is outside the original 31 index subsets.
    ddl = "CREATE UNIQUE INDEX chosen ON bookings(tenant, request_key) WHERE payload = '0'"

    def query(writes):
        with closing(sqlite3.connect(":memory:", isolation_level=None)) as con:
            con.execute(
                "CREATE TABLE bookings(tenant TEXT, local_intent TEXT, request_key TEXT, payload TEXT, attempt_no INTEGER)"
            )
            con.execute(ddl)
            con.executemany(
                "INSERT INTO bookings VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING", writes
            )
            return con.execute(
                "SELECT tenant,local_intent,payload FROM bookings ORDER BY 1,2,3"
            ).fetchall()

    main = [
        ("north", "1", "k7", "0", 1),
        ("north", "1", "k7", "0", 2),
        ("north", "2", "k9", "0", 1),
        ("south", "1", "k7", "0", 1),
    ]
    counter = [("north", "1", "k7", "1", 1), ("north", "1", "k7", "1", 2)]

    def measured(trace):
        actual = query(trace)
        expected = sorted({(w[0], w[1], w[3]) for w in trace})
        return {
            "writes": trace,
            "expected": expected,
            "actual": actual,
            "pass": actual == expected,
        }

    return {
        "index_sql": ddl,
        "primary_witness": measured(main),
        "different_payload_retry": measured(counter),
    }


def record(docs):
    report = {
        "schema": "stateproof-secondary-equivalence-and-scope-v1",
        "timing": "Supplementary, specified after measuring the primary study. Does not revise the frozen task or any prior result.",
        "equivalence": grouped_behavior(docs),
        "outside_family": out_of_family(),
    }
    report["sha256"] = hashlib.sha256(
        json.dumps(
            report, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    if a.out.exists():
        p.error("Choose a new output file")
    v = record(ROOT / "docs")
    with a.out.open("x") as f:
        json.dump(v, f, indent=2)
        f.write("\n")
    print(
        "Equivalent groups:",
        v["equivalence"]["groups"],
        "valid groups:",
        v["equivalence"]["valid_groups"],
        v["equivalence"]["false_approvals_by_group"],
    )
    print(
        "Out-of-family partial index:",
        v["outside_family"]["primary_witness"]["pass"],
        v["outside_family"]["different_payload_retry"]["pass"],
    )
