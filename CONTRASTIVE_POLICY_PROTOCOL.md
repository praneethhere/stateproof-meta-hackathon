# Prospective synthetic contrastive-policy challenge — Nov 4, 2026

**Designed before any Muse call on this fixture. Do not change labels or descriptions after seeing a result.** This is a separate follow-up, not a modification of the November 4 seven-operation policy experiment.

## Hypothesis to challenge

Can Muse Spark 1.3 distinguish explicit duplicate-suppression guarantees from visually similar descriptions in which the *same keys, headers and retry language* appear but the semantics explicitly permit an additional effect?

## Frozen dataset and score

- Six hand-authored **minimal semantic pairs** split into two predeclared fixtures, `contracts/contrastive_semantics_a.json` and `contracts/contrastive_semantics_b.json`, each with three protected/unprotected pairs plus one GET excluded from classification. Each run sees **six mutating operations** in varied safe/unsafe order; combined coverage is **12 mutations**, balanced six/six. All operation IDs are opaque, non-semantic strings. Protected/unprotected labels and pair mapping are recorded separately in `contracts/contrastive_pair_map.json` and are **never** supplied to the Meta API. The existing contract loader intentionally allows at most eight operations; do not relax that limit.
- The target is only a document-interpretation classification: `retry_same_key` for explicitly enforced suppression, `verify_then_escalate` otherwise. Both require an exact public-document quote. The text itself contains the discriminating clauses. The opaque operation IDs, descriptions, pair mapping and private simulator labels were authored by the project team and are **not independent or naturally sampled**.
- Primary: policy classification `matched/12` and number of pairs in which both interpretations are correct (`0–6`). Per-case classification rows must be published, including errors and cases with no valid model response.
- Control strategies: `conservative`, `always_retry`, and the repository's deliberately weak `naive_keyword` heuristic, plus `oracle_reference` which sees private labels and is not a deployable model baseline. Compare **classification accuracy**; report correct final states separately because the trusted enforcing adapter can mask policy errors.
- Secondary: 24 fresh, isolated HTTP/SQLite scenarios across both fixtures (two commit-boundary faults per write) using the deterministic readback-first actor and verified enforcement, not a new live Muse recovery episode.
- One Muse run **per fixture** (two planned calls total) with `reasoning.effort=high` is the initial prospectively registered attempt for each. Do not rerun simply to select a better score. Errors must be journaled; a retry for service failure must be disclosed. No statistical superiority or generalization claim is supported by one result.

## Integrity constraints

- Commit both fixtures, the pair mapping and protocol to GitHub **before** the paid model call. Save `git rev-parse HEAD` and hash of the public portion in the resulting receipt.
- Never send `private_simulator` to the model; do not edit the fixture, protocol, or rules after observing the output.
- A policy cannot authorize an external write without a separately configured trusted server capability in this simulator. The 24-case executor has independent SQLite ground truth.
- All data is synthetic. API evidence remains under ignored `evidence/`; only sanitized pages and receipts are manually reviewed and exported.
- A model outcome of 12/12 would show one success on an author-designed promptable semantic task, not a new research contribution or general superiority to stronger language understanding baselines.
