# When the ledger count is right and the bookings are wrong

**StateProof CrashLab · November 4, 2026**
[Run the four-write study](https://praneethhere.github.io/stateproof-meta-hackathon/intent-study.html) · [Frozen specification](INTENT_STUDY_PROTOCOL.md) · [All measured adapter grades](docs/intent-study-evidence.json) · [Raw SQLite observations](docs/intent-observations.jsonl.gz)

A retry can create a duplicate while an unrelated customer's booking disappears. A total of three rows then agrees with the expected total of three. This study asks exactly how many appends a single empty-database test needs to detect that kind of error in a specified family of retry adapters. The model-free reference test is complete. The separate [Muse test-design receipt](docs/intent-muse.json) states whether a new model plan was observed and how it scored.

## One witness

North and South are allowed to use the same local booking IDs and request keys. North's bookings **A** and **B** are independent. South's **C** uses the same local ID and key as North's **A**. The three business payloads in this witness are identical. Send `A, A, B, C`. The second A is a retry. All four appends reach the adapter. The expected business ledger contains one copy of each of A, B and C.

| Client or index identity | Actual effects, ignoring order | Count check | Full business-state check |
|---|---|---|---|
| Tenant and request key | A, B, C | Pass | Pass |
| Request key alone | A, B | Fail | Fail — South's C is missing |
| Request key and attempt number, shared across tenants | A, A, B | Pass | Fail — an extra A offsets the missing C |

The original workbench's repeat probe intentionally measures only one booking. In a multi-tenant adapter, repeating A can produce exactly one effect even when the same adapter later suppresses C. This specifies the boundary of the original demonstration. It does not change its recorded single-intent results.

## Minimum for the declared family

The implementation family contains all 31 nonempty UNIQUE index subsets of five fields, plus an adapter without a unique index. The fields are tenant, local booking ID, request key, stable payload and per-intent attempt number. Each row is appended with `ON CONFLICT DO NOTHING`. The reference contract requires one correct row per distinct tenant and local booking. The client reuses all business fields on retry. Keys are unique within a tenant and may recur elsewhere. In this family, six index choices satisfy the contract and 26 do not.

**Sufficiency.** In the fixed trace `AABC`, a missing uniqueness constraint or an index containing the changing attempt number allows the second A. With attempt number absent, an index omitting tenant collides on A and C, because all their remaining fields are equal. An index including tenant but neither local booking ID nor request key collides on A and B because their payloads are equal. These cases exhaust the 26 invalid designs. Each valid index contains tenant and at least one of the two per-tenant identifiers and excludes attempt number. It suppresses only the repeat and preserves the three intended effects. Comparing tenant, local ID and payload **with multiplicity** distinguishes all 32 designs in this test.

**Necessity.** Any trace with at most three writes either contains no retry or contains at most two distinct intents. Without a retry the no-index adapter can produce the required final state. When the at-most-two intents share a tenant, an invalid globally scoped request-key adapter can produce the required state. When they belong to different tenants, an invalid tenant-only adapter can do so. A one-intent trace likewise admits a bad adapter. In each case an invalid design has the same final business rows as a valid design. No decision using only those rows can separate them on that trace. This lower bound covers single fixed nonadaptive schedules, an initially empty store and the declared workload. It does not cover schema introspection, multiple independent resets, arbitrary APIs, intermediate privileged observations or concurrent histories.

## Enumeration and ablations

Every ordered sequence of lengths one through four over A–D was executed under all 16 assignments of stable binary payloads to the four logical intents. Each sequence/payload cell was run against 32 SQLite adapters. A second connection queried committed rows. This produced **174,080 deterministic adapter trials**. Some payload assignments coincide on the intents a particular trace actually uses; these are explicitly enumerated combinations, not independent samples. An independently written, standard-library key-projection checker reproduced every row in all trials. It also rechecked the controls and the external broker evidence.

| Writes | Ordered schedules | Schedule/payload combinations | Combinations classifying every adapter |
|---:|---:|---:|---:|
| 1 | 4 | 64 | 0 |
| 2 | 16 | 256 | 0 |
| 3 | 64 | 1,024 | 0 |
| 4 | 256 | 4,096 | 352 |

| Equal four-write budget | Readout | Invalid adapters approved / 26 | Correct classifications / 32 |
|---|---|---:|---:|
| AAAA | Total rows | 9 | 23 |
| ABCD | Business tuples with multiplicity | 7 | 25 |
| AABC | Total rows | 8 | 24 |
| AABC | Distinct business tuples, duplicates ignored | 7 | 25 |
| AABC | Business tuples with multiplicity | 0 | 32 |

All five comparisons accepted all six valid designs. On the constant-payload task given to the optional model planner, 88 of the 256 possible four-write sequences are adequate with the multiset readout. No such sequence is adequate with either of the other two readouts. The exact human reference is a strong non-model baseline. A model matching it on one prompt cannot establish superiority over engineers, reliability in repeated runs or a new general-purpose method.

## What changes when equivalent indexes count only once?

This secondary analysis was added after inspecting the main results. The 32 syntactic index choices yield **13 distinct observed behaviors** over the entire finite corpus. Six valid index choices share the same correct behavior. Across the **12 distinct invalid behaviors**, four-write repeat-only counting falsely approves 5, the mixed AABC row count approves 4, and the AABC multiset check approves 0. The latter result also holds without giving additional weight to behaviorally equivalent keys.

We deliberately tried to break the witness outside its assumptions. SQLite permits a partial tenant/key index that enforces uniqueness only when `payload = '0'`. It passes the `AABC` demonstration on payload 0, but `AA` on payload 1 produces two bookings for one intent. This concrete counterexample blocks a claim of general certification. [Equivalence groups and out-of-family tests](docs/intent-boundaries.json)

## Transfer to two unmodified queue engines

The same `AABC` witness was issued on a disposable **Redis Streams 8.6.0** server and on **NATS JetStream 2.15.2**. For Redis, a separate connection confirmed the first append before the sender closed without reading its reply. For NATS, the initial application acknowledgement went to an inbox with no subscriber; the observer confirmed the append before the remaining writes. The observer then retrieved actual stream entries with Redis `XRANGE` or a separate NATS client's `get_msg`. All six engine/mapping outcomes matched the table in “One witness” and were reproduced on a second fresh pair of server processes.

NATS used memory storage with a 60-second duplicate window. All sends were immediate, single-server and sequential. These are intentionally chosen **client** key mappings. The servers behaved consistently with their documented deduplication scope. The evidence concerns stored stream entries, not disk durability, downstream delivery, actual bookings or a vendor defect. [Raw commands, replies and entries](docs/intent-broker-evidence.json) · [Redis documentation](https://redis.io/docs/latest/develop/data-types/streams/idempotency/) · [NATS documentation](https://github.com/nats-io/nats.docs/blob/master/using-nats/jetstream/model_deep_dive.md#message-deduplication)

## A harder check on the earlier Muse result

The original six-pair experiment and both published Muse receipts are unchanged. We added two retrospective comparators with a scoring rule fixed before running either new control. The DeBERTa checkpoint was obtained from a pinned public revision, and the weight and tokenizer files were verified against the upstream tree. There was no tuning after inference. The model was given the operation description and two fixed hypotheses, and the larger entailment logit selected the policy. The retrieval model trained only on the seven earlier labeled operations.

| Policy source | Correct / 12 | Complete pairs / 6 |
|---|---:|---:|
| Recorded Muse Spark 1.3 | 12 | 6 |
| Frozen `cross-encoder/nli-deberta-v3-small` | 11 | 5 |
| Character n-gram nearest neighbor | 7 | 1 |
| Each of four previously published simple rules | 6 | 0 |

The sole NLI error was the safe webhook clause `op_r2b6`. The new comparators saw one description at a time; Muse received six per call, including their partners, and also had to cite an exact supporting clause. The one-item difference does not establish a general model ranking. [All predictions and logits](docs/intent-semantic-controls.json) · [Original Muse evidence](docs/contrast-evidence.json) · [Pinned NLI checkpoint](https://huggingface.co/cross-encoder/nli-deberta-v3-small/tree/fa2804872c3b4bd748f38c0185cc85775361e735)

## Boundaries and related work

- **LIMBO** already benchmarks ambiguous writes, omitted effects and duplicates across agent, harness and tool-contract conditions, and counts effects matching individual requirements on multi-action tasks. StateProof's scoped contribution here is the minimum fixed witness for this explicit index family, its exhaustive check, and the replicated compensated-collision example. [Li, 2026](https://arxiv.org/abs/2609.29095)
- **τ-bench** evaluates an agent against a goal database state. **Jepsen** provides established set/history checkers and directly tested NATS for other failure modes. We do not claim to introduce state-based correctness or queue testing. [τ-bench](https://arxiv.org/abs/2406.12045) · [Jepsen checkers](https://jepsen-io.github.io/jepsen/jepsen.checker.html) · [Jepsen on NATS](https://jepsen.io/analyses/nats-2.12.1)
- **Database schema mutation testing** predates this work, including experiments on multi-column integrity constraints. AWS also documents the role of caller scope and the distinction between identical requests and identical intent. This study offers a reproducible finite result. Worldwide priority, external adoption and production failure prevalence are unestablished. [McMinn, Wright and Kapfhammer](https://eprints.whiterose.ac.uk/id/eprint/96273/) · [AWS Builders’ Library](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
- Four additional hackathon repositories informed the evaluation design. CounterForge separates screening from fresh confirmation. Metamorph deliberately mutates a SQLite row to test its oracle. Patch Cross-Examiner tests order-preserving deduplication with a counterexample. Yebo tests the identity and scope of an approved effect. Our experiments, proof and implementation use StateProof's own adapters and public upstream engines; competitor source was inspected, not incorporated. [CounterForge verifier](https://github.com/ottorafaelcihak/CounterForge/blob/3191713855dcacd0c80882477db81486bdd67cfb/scripts/verify_export.py) · [Metamorph controls](https://github.com/Meta-Project2026/Metamorph/blob/e0e971bd8d8c3d1a28c8332d42748e78e59a970a/packages/oracle/src/controls.ts) · [Patch Cross-Examiner test](https://github.com/Ps23102004/patch-cross-examiner/blob/8c546201edf7e09d65593867a4cebbd8cd2a76f6/examples/01_order_preserving_dedup/test_counterexample.py) · [Yebo tests](https://github.com/Unclefole/yebo-muse-agent/blob/ec225014debe73b5e4a5973ec189577b2f754c57/test/adversarial.test.ts)

## Reproduce

From the repository root, Python 3.13 can run both the native SQLite census and the independent pure-Python verifier. The public raw archive is small and contains only synthetic data. Each uncompressed line contains `[schedule, payload_assignment, observed_business_rows_by_adapter]`; the adapter order is in the summary. Its deterministic uncompressed SHA-256 is `79954dd3dcb1f95f415c9d134b29e6cf1dec97b9cedbdb9532f734eb227d8258`.

```bash
python research/verify_intent.py
python -m stateproof.intent_study --out /tmp/intent-study.json --raw-gz /tmp/intent-trials.jsonl.gz
```

Engine integration uses `nats-py==2.16.0`, a local `redis-server` and a local `nats-server`. The checked Linux experiments used upstream Redis 8.6.0 source SHA-256 `d7e5f65f0bb0b4753d0cf98a60f5409a7c9b430ff8ac3397d336260cf64e5a6e` and NATS 2.15.2 Linux amd64 release archive SHA-256 `67cb8e10bc6f0c4b47f75a728529a20953dbae2a4f9a4a52ae8517d65ae303ff`. Both were checked against their respective upstream release checksums. [Redis hashes](https://github.com/redis/redis-hashes) · [NATS release](https://github.com/nats-io/nats-server/releases/tag/v2.15.2)

```bash
python -m stateproof.intent_brokers --redis /path/to/redis-server --nats /path/to/nats-server --out /tmp/intent-brokers.json
```

To reproduce the retrospective NLI run, install CPU PyTorch 2.8.0, `transformers==4.55.4`, `sentencepiece` and `protobuf` in an isolated environment. Fetch the files listed in `research/nli-files.json` at the specified Hugging Face revision, then run the following. Inference is local and the runner checks the snapshot before loading it.

```bash
python -m stateproof.intent_semantic_controls --model-dir /path/to/pinned/snapshot --out /tmp/semantic-controls.json
```

The optional `stateproof.intent_muse` module is the only new component that calls the Meta API. It requires a published freeze, explicit billing flags and a local key, and records the first attempt. Its proposal is scored by actually running SQLite. A failed or incorrect first proposal is publishable. Offline verification of the deterministic result requires no account, network service or model call.
