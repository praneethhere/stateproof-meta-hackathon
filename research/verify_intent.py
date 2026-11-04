"""Independent stdlib reconstruction. Does not import StateProof or call SQLite."""

import argparse
from collections import Counter
import gzip
import hashlib
from itertools import combinations, product
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ("tenant", "local_intent", "request_key", "payload", "attempt_no")
SUBSETS = [v for size in range(6) for v in combinations(range(5), size)]
ACTIONS = {
    "A": ("north", "1", "k7"),
    "B": ("north", "2", "k9"),
    "C": ("south", "1", "k7"),
    "D": ("south", "2", "k9"),
}


def canonical_sha(obj):
    return hashlib.sha256(
        json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def load_hashed(path):
    data = json.loads(path.read_text())
    checksum = data["sha256"]
    if checksum != canonical_sha({k: v for k, v in data.items() if k != "sha256"}):
        raise ValueError(f"Wrong summary checksum: {path.name}")
    return data


def project(seq, payload):
    count = Counter()
    calls = []
    for alias in seq:
        count[alias] += 1
        calls.append((*ACTIONS[alias], payload["ABCD".index(alias)], count[alias]))
    expected = sorted({(c[0], c[1], c[3]) for c in calls})
    observed = []
    for subset in SUBSETS:
        seen = set()
        effects = []
        for c in calls:
            identity = tuple(c[i] for i in subset)
            if not subset or identity not in seen:
                effects.append([c[0], c[1], c[3]])
            seen.add(identity)
        observed.append(sorted(effects))
    return expected, observed


def verdict(matrix, expected, mode):
    ref = set(expected)
    if mode == "count":
        return [len(v) == len(expected) for v in matrix]
    if mode == "identity_set":
        return [set(map(tuple, v)) == ref for v in matrix]
    if mode == "identity_multiset":
        return [sorted(map(tuple, v)) == expected for v in matrix]
    raise ValueError("Unknown oracle")


def verify(docs):
    if not __debug__:
        raise RuntimeError("Verification requires Python assertions to be enabled")
    summary = load_hashed(docs / "intent-study-evidence.json")
    names = ["+".join(COLUMNS[i] for i in s) or "no_unique_index" for s in SUBSETS]
    assert names == summary["adapter_order"]
    fingerprints = [hashlib.sha256() for _ in names]
    counts = [0] * 32
    aggregated = Counter()
    random = Counter()
    sha = hashlib.sha256()
    n = 0
    valid = [bool(0 in s and (1 in s or 2 in s) and 4 not in s) for s in SUBSETS]
    with gzip.open(docs / "intent-observations.jsonl.gz", "rb") as raw:
        for length in range(1, 5):
            for actions in product("ABCD", repeat=length):
                script = "".join(actions)
                for bits in product("01", repeat=4):
                    payload = "".join(bits)
                    line = raw.readline()
                    sha.update(line)
                    trace, fields, sql = json.loads(line)
                    if trace != script or fields != payload:
                        raise ValueError("Missing or reordered raw trace")
                    expected, predicted = project(script, payload)
                    if sql != predicted:
                        raise ValueError(
                            f"Independent key-projection model contradicts SQLite on {script}/{payload}"
                        )
                    for fp, adapter_rows in zip(fingerprints, predicted, strict=True):
                        fp.update(
                            json.dumps(adapter_rows, separators=(",", ":")).encode()
                            + b"\n"
                        )
                    states = verdict(sql, expected, "identity_multiset")
                    n += len(sql)
                    for i, state in enumerate(states):
                        counts[i] += not state
                    aggregated[length] += int(states == valid)
                    if length == 4 and payload == "0000":
                        for mode in ("count", "identity_set", "identity_multiset"):
                            random[mode] += int(verdict(sql, expected, mode) == valid)
        if raw.read(1):
            raise ValueError("Unexpected extra observation")
    assert (
        n == summary["trial_count"]
        and sha.hexdigest() == summary["ordered_outcomes_sha256"]
    )
    assert {
        r["writes"]: r["combinations_classifying_all_32"] for r in summary["search"]
    } == dict(aggregated)
    assert summary["counts_of_histories_with_wrong_state"] == dict(zip(names, counts))
    assert [c == 0 for c in counts] == valid
    for row in summary["campaigns"].values():
        expected, matrix = project(row["schedule"], "0000")
        grades = verdict(matrix, expected, row["readout"])
        assert [x["actual"] for x in row["adapters"]] == matrix
        assert [x["approved"] for x in row["adapters"]] == grades
        assert [x["reference_valid"] for x in row["adapters"]] == valid
        assert row["correctly_classified"] == sum(a == b for a, b in zip(grades, valid))
        assert row["false_approvals"] == [
            k for k, a, b in zip(names, grades, valid) if a and not b
        ]
        assert row["false_refusals"] == [
            k for k, a, b in zip(names, grades, valid) if not a and b
        ]
    external = load_hashed(docs / "intent-broker-evidence.json")
    expected, proj = project("AABC", "0000")
    keys = {"tenant_scoped": (0, 2), "global_key": (2,), "global_key_attempt": (2, 4)}
    assert {e["engine"] for e in external["engines"]} == {
        "Redis Streams",
        "NATS JetStream",
    }
    for engine in external["engines"]:
        assert {c["mapping"] for c in engine["cases"]} == set(keys) and len(
            engine["cases"]
        ) == 3
        for c in engine["cases"]:
            observed = sorted(
                [r["body"]["tenant"], r["body"]["local_intent"], r["body"]["payload"]]
                for r in c["entries"]
            )
            assert (
                observed
                == proj[SUBSETS.index(keys[c["mapping"]])]
                == c["observed_business_rows"]
            )
            assert len({str(r["server_seq"]) for r in c["entries"]}) == len(observed)
            assert c["count_pass"] == (len(observed) == len(expected)) and c[
                "identity_multiset_pass"
            ] == (list(map(tuple, observed)) == expected)
    secondary = load_hashed(docs / "intent-boundaries.json")
    equivalence = secondary["equivalence"]
    domains = {}
    for fingerprint, name in zip(fingerprints, names, strict=True):
        domains.setdefault(fingerprint.hexdigest(), []).append(name)
    assert domains == equivalence["members_by_outcome_fingerprint"]
    assert len(domains) == equivalence["groups"]
    for ident, campaign in summary["campaigns"].items():
        assert (
            sum(g[0] in campaign["false_approvals"] for g in domains.values())
            == equivalence["false_approvals_by_group"][ident]
        )
    outside = secondary["outside_family"]
    for part in ("primary_witness", "different_payload_retry"):
        trial = outside[part]
        seen = set()
        observed = []
        for tenant, local_id, key, payload, attempt in trial["writes"]:
            if payload != "0" or (tenant, key) not in seen:
                observed.append([tenant, local_id, payload])
                seen.add((tenant, key))
        assert sorted(observed) == trial["actual"]
        assert (sorted(observed) == trial["expected"]) == trial["pass"]
    assert (
        outside["primary_witness"]["pass"]
        and not outside["different_payload_retry"]["pass"]
    )
    nli = load_hashed(docs / "intent-semantic-controls.json")
    pairs = json.loads((ROOT / "contracts/contrastive_pair_map.json").read_text())[
        "pairs"
    ]
    truth = {p["safe_id"]: True for p in pairs} | {p["unsafe_id"]: False for p in pairs}
    for g in nli["grades"].values():
        rows = g["rows"]
        assert set(rows) == set(truth)
        assert all(r["correct"] == (r["retry"] == truth[k]) for k, r in rows.items())
        assert g["matched"] == sum(r["correct"] for r in rows.values())
        assert g["pairs_both"] == sum(
            rows[p["safe_id"]]["correct"] and rows[p["unsafe_id"]]["correct"]
            for p in pairs
        )
    original = json.loads((docs / "contrast-evidence.json").read_text())
    assert (
        nli["original_summary_sha256"]
        == original["receipt_sha256"]
        == canonical_sha({k: v for k, v in original.items() if k != "receipt_sha256"})
    )
    for row in original["operations"]:
        assert nli["grades"]["recorded_muse"]["rows"][row["operation_id"]]["retry"] == (
            row["muse_action"] == "retry_same_key"
        )
    pin = json.loads((ROOT / "research/nli-files.json").read_text())
    assert (
        nli["nli"]["weights_and_tokenizer_sha256"] == pin["sha256"]
        and nli["nli"]["revision"] == pin["revision"]
    )
    entail = nli["nli"]["labels"]["entailment"]
    for row in nli["grades"]["frozen_nli"]["rows"].values():
        assert (
            row["entailment_retry"] == row["logits"][0][entail]
            and row["entailment_verify"] == row["logits"][1][entail]
        )
        assert row["retry"] == (row["entailment_retry"] > row["entailment_verify"])
    plan = json.loads((docs / "intent-muse.json").read_text())
    if plan["status"] in ("scored", "unscored"):
        assert plan["sha256"] == canonical_sha(
            {k: v for k, v in plan.items() if k != "sha256"}
        )
        assert (
            plan["model_request_number"] == 1
            and plan["protocol_sha256"] == summary["protocol_sha256"]
        )
    if plan["status"] == "scored":
        assert plan["response_id"].startswith("resp_")
        proposal = plan["proposal"]
        expected, matrix = project(proposal["schedule"], "0000")
        chosen = verdict(matrix, expected, proposal["readout"])
        ideal = verdict(matrix, expected, "identity_multiset")
        score = plan["score"]
        assert (
            score["schedule"] == proposal["schedule"]
            and score["readout"] == proposal["readout"]
        )
        assert score["correctly_classified"] == sum(
            a == b for a, b in zip(chosen, valid)
        )
        assert score["same_trace_with_multiset_correct"] == sum(
            a == b for a, b in zip(ideal, valid)
        )
        assert score["false_approvals"] == [
            k for k, a, b in zip(names, chosen, valid) if a and not b
        ]
        assert score["false_refusals"] == [
            k for k, a, b in zip(names, chosen, valid) if not a and b
        ]
    elif plan["status"] not in ("not_run", "unscored"):
        raise ValueError("Unexpected first-attempt status")
    return {
        "sqlite_observations_checked": n,
        "ordered_outcomes_sha256": sha.hexdigest(),
        "adequate_by_writes": dict(aggregated),
        "fixed_payload_uniform_4_write_successes_out_of_256": dict(random),
        "broker_cases": 6,
        "distinct_observed_behaviors": len(domains),
        "outside_family_counterexample_verified": True,
        "muse_test_design_status": plan["status"],
        "semantic_scores": {
            k: [v["matched"], v["pairs_both"]] for k, v in nli["grades"].items()
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    a = parser.parse_args()
    print(json.dumps(verify(a.docs), indent=2))
