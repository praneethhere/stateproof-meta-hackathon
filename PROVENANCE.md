# StateProof CrashLab — submission provenance

**Meta Global AI Developer Hackathon 2026 · Indie Developer · Push the Frontier**

The **submitted entry is StateProof CrashLab**, not the earlier StateProof Lab exploratory prototype.

## Chronology and limits of verification

| Date (America/Chicago) | Public Git record | Explanation |
| --- | --- | --- |
| October 26, 2026 | No public commit | Earlier exploratory StateProof Lab evidence-gating reference code includes a `PREBUILD` label dated October 26. This is not submitted as hackathon work. |
| October 29, 2026, 7:40 PM | `55fd291` | First public Git checkpoint of an already working StateProof Lab prototype; its commit time is **not proof of original authoring time**. |
| October 29, 2026, 11:24 PM | `11952b4` | First public integration of the separate CrashLab contract planner, synthetic evaluation, and public showcase. |
| October 30, 2026, 12:40 PM | `0e84668` | First public integration of CrashLab's loopback HTTP fault experiments, SQLite oracle, retry authorization, post-hoc replay, and second interactive case-study page. |
| November 2, 2026 | See subsequent public commits | Submission cleanup and a separate contract-to-policy evaluation added after external code review; timestamps and results should be verified in Git and local receipts. |

The event page says the hackathon began with the October 26 kickoff; the participant guide identifies October 27–November 4 as the building period. We take the conservative approach and do not present the October 26 prebuild implementation as new work.

The earlier StateProof Lab source and its tests were removed **from the current submitted working tree** in an ordinary follow-on Git commit. Its historical commits remain intact and are visible; this is **not an attempt to conceal prior work**. CrashLab modules do not import the earlier prototype. The general idea of checking ambiguous post-commit acknowledgments with an independent ledger was explored earlier and is not claimed as new.

The CrashLab-specific public commits show availability by October 29–30, but Git timestamps alone cannot establish when every underlying line was authored. This document is not a certification that all code was authored in an eligible period. If any CrashLab source predates the eligible window, that fact must be disclosed accurately rather than inferred from Git commit dates.

## AI assistance and independent review

ChatGPT assisted with prototype design and implementation. Claude Opus 5.5 provided an independent adversarial review on November 2, which prompted clearer limitations, removal of prebuild material from the submitted tree, and additional work on evidence and the policy evaluation. Model-generated analysis and code were inspected and tested; AI assistance is not presented as independent authorship of benchmark holdouts or results.

## What the evidence is

- The HTTP and SQLite experiments are **isolated, synthetic**, not production services.
- The observed Muse actor episode is separate from deterministic actor tests and from post-hoc counterfactual replay.
- The first interrupted six-condition Muse experiment and its resumed follow-up are distinct; the full live matrix has **one observed episode per condition**.
- The original private receipts and frozen holdout simulator data are not independently reproducible from public source alone. Local receipt hashes establish consistency only with the corresponding local files, not external attestation.
- The submitted contract policy tests are **small synthetic examples**. Even when a Meta model proposes a policy, a deterministic trusted adapter enforces server-side retry authorization and a deterministic client runs the evaluation.
- Lost acknowledgments, stale readbacks, idempotency keys, and retry authorization are established engineering/research topics; this project does **not** claim to invent those mechanisms.

See [POLICY_PROTOCOL.md](POLICY_PROTOCOL.md) for the new policy experiment's pre-run specification, and [README.md](README.md) for reproducibility instructions.

## November 4 executable workbench

The booking workbench executes synthetic reservation writes in the visitor’s browser. The SQLite engine is an unmodified sql.js distribution with its upstream license in `docs/vendor`. The experiment selection, index controls, independent probes, Python regression exporter and recorded-policy integration were added for CrashLab with ChatGPT assistance. The browser reuses the existing Muse booking policy and makes zero new inference calls. The recorded HTTP agent runs remain separate.

The Redis Streams compatibility check was added on November 4. The unmodified Redis 8.6.0 tarball was verified against the upstream `redis/redis-hashes` SHA-256 (`d7e5f65f0bb0b4753d0cf98a60f5409a7c9b430ff8ac3397d336260cf64e5a6e`). Only our client, the measured rows and the reproduction command are included. Redis documents the command semantics. No Muse call is attributed to the Redis experiment.

The contrast page table labels and paired-score display were edited after scoring. The two model receipts, recorded summary, frozen fixtures and pre-call addendum are unchanged.

## November 4 intent-identity study

The new finite test family, proof, exhaustive SQLite study, Redis and NATS client mappings, independent checker and live browser grader were developed after the previously published hackathon results. ChatGPT assisted with design, implementation and verification. The twelve-item DeBERTa and nearest-description comparisons are retrospective; the original model receipts are preserved byte for byte. The protocol was locally committed before measurement. The external write path, if invoked, is one later frozen Muse test-design call. Its status and exact outcome appear in `docs/intent-muse.json`. See [methods and prior work](INTENT_STUDY.md) for boundaries and upstream code and model provenance.
