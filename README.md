# StateProof (Meta Global AI Developer Hackathon 2026)

**Milestone 1: deterministic synthetic baseline only.** No Meta model calls are made in this version. The simulated retry client is not an AI agent.

This baseline demonstrates a lost HTTP response *after* a payment commits. A client retries and reports success, but the actual synthetic ledger can contain two charges unless idempotency is enforced.

## Run

From the repository root with the existing Python virtual environment activated:

```bash
python -m stateproof
python -m pytest -q
```

The two cases are isolated in separate in-memory SQLite ledgers. The verifier independently reads the ledger, asserts exactly one charge, and checks the expected total. All account/order details are invented; no real payments, banks, or credentials are involved.

## Interpretation

- `missing_idempotency`: client reports success, verifier flags **two synthetic charges**.
- `idempotency_enabled`: client reports success, verifier confirms **one synthetic charge**.

The point is **not** novelty or a completed AI-agent testing platform. Similar timeout/retry failures and deterministic checks are well established. Next milestones: add an allowlisted catalogue of fault experiments; use `muse-spark-1.3` tool calls to select experiments; compare it fairly against static strategies using held-out synthetic scenarios; evaluate false positives and budgeted detection rates; show an honest, runnable demo.

## Submission integrity

The hackathon's participant guide requires newly built work, a public repository, and a three-minute demo showing what was actually implemented. Keep all work and commit history attributable and do not include DuraTrace unpublished code, data, or credentials.
