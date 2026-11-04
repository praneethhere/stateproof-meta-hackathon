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
