# Post-hoc synthetic contract-drift audit — Nov 4, 2026

## Question

Can a local executable audit expose a contradiction between a **saved Muse Spark 1.3 policy claim** and the behavior of an isolated HTTP API implementation, then block an unauthorized retry? This is an engineering demonstration, not a novel research claim or a natural measurement of vendor contract drift.

## Original inputs and historical separation

- The **saved** Muse policy was generated earlier on Nov 4 against the seven-write synthetic contract, with response ID `resp_6aeb460fbf3f54cd3a6f4779`. Its receipt and hash are supplied at runtime; this script makes **zero** Meta API calls.
- Another **separate** live Muse actor experiment on Nov 4 used a hard-stop boundary. Its saved M8 receipt is optional input. The model continued after denial and reported DONE with one independent SQLite effect. It is **not** a continuation of the original M7 failure or the M8B replay.
- The original synthetic contract has seven mutating operations and a deterministic private implementation configuration used to construct the lab. Only the public descriptions were sent to Muse.

## Deliberate synthetic intervention (not vendor behavior)

Modify the sandbox implementation for **exactly two** operations without changing its published descriptions or the saved Muse policy:

1. `reserve_slot`: docs and saved Muse policy promise request-key deduplication. The synthetic implementation is switched from `request_key` to `none`. Two same-key HTTP calls must produce two independent SQLite rows (critical disagreement).
2. `charge_freight`: docs warn each request creates a charge. The synthetic implementation is switched from `none` to `request_key`. Two same-key HTTP calls produce one row, but the original documentation still gives no retry guarantee. Maintain conservative refusal.

All other five operations remain unchanged. This controlled mismatch was selected by the author to show how an audit works; it is not an unbiased sampled failure or a naturally observed behavior change.

## Probe and guard protocol

- For every write operation, create a fresh temporary loopback HTTP + file-backed SQLite service with the selected synthetic behavior, and make **two** calls with the same request key. Read the database directly; do **not** use the implementation label to decide the probe's observed count.
- Compare the observed duplicate behavior to the original recorded Muse policy interpretation.
- A retry in a separate lost-acknowledgment and stale-read scenario is only enabled when **both** the policy calls for same-key retry **and** the local sandbox probe did not produce a duplicate. The underlying guard also checks the local service's deduplication mode. All contradictory or unsupported claims fail closed.
- Run each of seven writes under two failure boundaries: dropped acknowledgment **after** committing and disconnected request **before** committing. This is **14** deterministic sandbox trials, with a readback-first deterministic client. The live Muse agent does not execute this matrix.
- Keep the entire saved receipt intact on disk. Public pages contain a bounded, source-checked summary plus optional sanitized receipt from the separate live Muse guard experiment.

## Required reporting

Report both kinds of doc/runtime mismatch, all 14 final states, duplicate effect count and incomplete operations. Show the hard-stop liveness cost. Do not describe a two-call local probe as proof of production exactly-once execution, and do not call the deliberate simulated drift a real incident.

## Claim boundaries

- A recorded Muse policy was **interpreted**, then challenged by a deterministic synthetic fault-injection system; the model was not asked to adapt to the changed implementation.
- The guard's correctness comes from a deterministic boundary, not from model instructions.
- The initial seven-operation Muse policy result is small and uses explicit guarantees. Simple and always-retry controls can tie its final-state outcomes when a trusted adapter has implementation knowledge.
- All mechanisms rely on established work on idempotency, commit/acknowledgment ambiguity, independent state checks and retry authorization. No research novelty or broad model superiority is claimed.
