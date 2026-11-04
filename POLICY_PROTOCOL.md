# CrashLab contract-to-retry-policy experiment — protocol v1

**Protocol created before any new live Meta policy run.** This file specifies the evaluation; do not edit it to fit a later model result.

## Claim under test

Can Muse Spark 1.3 interpret a synthetic API contract's retry semantics and propose a per-operation **advisory** policy (`retry_same_key` or `verify_then_escalate`)? The proposed policy is never itself authorization to retry. A trusted local adapter only permits retrying if request-key deduplication is *actually* configured in the synthetic service.

No claim of novelty, statistical model superiority, or production-safe retry authorization follows from this experiment.

## Inputs and frozen scope

- Public synthetic contract: `contracts/policy_challenges.json`, eight operations (seven mutations and one GET), with a private simulator specification in the same file. The `private_simulator` section is never passed to Muse.
- Reference development fixture: `contracts/support_credit.json` (three synthetic writes).
- Model: `muse-spark-1.3`, Meta Model API Responses function calling, one `submit_retry_policy` response per run; `reasoning.effort=high` unless the run records an explicit deviation.
- Decision options: `retry_same_key` and `verify_then_escalate`; each selected with a short **exact quote** from the corresponding public operation description. Invalid schemas or invented quotes fail rather than silently receiving a score.
- Required API flags: `--strategy muse --live --accept-api-cost`. API failures are recorded as failures to obtain a result and are **not scored** as agent/policy failures.

## Controls and execution

- `conservative`: deny retries after ambiguous writes.
- `always_retry`: propose a same-key retry for every write, but the trusted adapter still denies it for operations without verified deduplication; deliberately include this strong negative control.
- `naive_keyword`: a deliberately weak, negation-insensitive keyword rule; do not portray as a strong baseline.
- `oracle_reference`: uses the hidden synthetic server specification and is an **upper reference**, not an independently deployable baseline.
- Each policy is applied to seven mutating operations under two fault conditions: lost reply **after** commit and connection closed **before** commit. The first post-write readback is stale zero. Each of the 14 trials gets a fresh local ThreadingHTTPServer and file-backed SQLite database.
- A deterministic readback-first client executes the proposed policy; it is **not** a new Muse recovery continuation. Only the policy text is model-produced. The oracle counts actual SQLite rows independently.

## Metrics and falsification

Report: policy classification matching the reference labels, number of correct final states, incomplete tasks, duplicated effects, and unsafe same-key recommendations denied by the trusted adapter. The possible uncomfortable outcome—`always_retry` tying Muse because the adapter already has verified server semantics—must be reported prominently. If Muse generates unsupported same-key recommendations, do not silently correct its reported policy or exclude the case. Include API errors and deviations in the journal.

The synthetic challenge may be too easy or strategically designed. Claims are limited to the exact operations and one policy output. These are exploratory demonstrations, **not measured failure rates across a model distribution**. Prior art includes LIMBO, Permission to Retry, RetryBench, and established provider idempotency protocols.

## Evidence and video labels

- Preserve raw local JSON under ignored `evidence/` and do not overwrite it.
- Export sanitized `docs/policy-evidence.json` and `docs/policy.html` only after a successfully completed live Muse run and manual privacy review.
- In the video, label the proposal as **RECORDED META API POLICY**, the 14 HTTP tests as **DETERMINISTIC CLIENT + REAL LOCAL HTTP/SQLite**, and older recovery content separately as **RECORDED MUSE EPISODE** or **POST-HOC REPLAY**.
- The exact time and Git hash of the protocol commit should precede the actual paid model call. No new model result is claimed until the user's API run has succeeded.
