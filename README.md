# StateProof CrashLab

**Contract-aware crash planning and reproducible fault evidence for stateful AI-agent workflows.**
Meta Global AI Developer Hackathon 2026 · Indie / Push the Frontier

> **What works:** Muse Spark 1.3 reads the *public documentation* of an unfamiliar synthetic API and proposes an operation to crash at a lost-acknowledgment boundary. A separate, allowlisted SQLite fault executor replays a bounded retry, and an independent state check determines whether the intended effect happened exactly once. CrashLab can export an executable regression test and a standalone interactive replay.
>
> **What it does not do:** It does not run faults against real services, independently generate production fixes, or prove that Muse is generally better than deterministic planners. Muse **selects the crash plan**; a deterministic client **performs the retries and reports success**.

## Demo

**[Open the interactive replay](docs/index.html)** — self-contained HTML, no login or API key. The published GitHub Pages version (when enabled) renders the same file. The animated timeline is a **new deterministic replay of saved crash plans**, not a captured live Muse execution trace.

The demonstration shows two independently authored synthetic workflows:

| Frozen challenge | Muse-selected operation | Muse: fault exposed? | Writes-first / keyword / single-seed random |
| --- | --- | --- | --- |
| Collection-visit booking | `book_collection_visit` | Yes | No / No / No |
| Hive-load dispatch | `dispatch_hive_load` | Yes | Yes / Yes / Yes, for `request_block_survey` |

**Recorded result:** Muse exposed a duplicate side effect in **2/2** frozen synthetic challenges; each heuristic exposed one in **1/2**. Synthetic severity-weighted scores were **8 vs. 2**. The random comparison uses **one fixed seed**, not a distribution. All four planners received **one operation selection per case**, and all compliant plans were tested at the same `after_commit_lost_ack` fault boundary.

These are **descriptive, exploratory results for just two deliberately constructed workflows**. They do not establish statistical significance, model superiority, general agent reliability, or measured real-world financial damage. The private holdout simulator definitions and frozen evidence are intentionally not published; the HTML contains sanitized results and re-executed synthetic timelines. The public development fixture below **is** independently runnable.

## Run locally

Python 3.13+ recommended. Install the pinned dependencies from `requirements.txt` in a virtual environment, then:

```bash
python -m pytest -q tests

python -m stateproof.crashlab \
  --contract contracts/support_credit.json \
  --strategy keyword \
  --html /tmp/crashlab_keyword.html
```

This **offline development example** demonstrates a duplicate credit in a synthetic in-memory ledger. It is **not** one of the two frozen challenge workflows. The keyword heuristic finds the same issue as Muse on this development case.

To run an **optional paid Muse planning call** against the public development contract, provide your own Meta Model API credential via `MODEL_API_KEY`, then explicitly opt in:

```bash
python -m stateproof.crashlab \
  --contract contracts/support_credit.json \
  --strategy muse --live --effort high \
  --out /tmp/crashlab_muse.json \
  --html /tmp/crashlab_muse.html
```

The public replay in `docs/index.html` **does not call Meta** and works offline.

## How it works

1. **Contract** — public operation descriptions, retry semantics, and business constraints are presented to Muse; private simulator definitions are not.
2. **Plan** — Muse proposes an allowlisted operation, fault phase, hypothesis, and *suggested* readback. The readback suggestion is not executed as a separate tool call in the frozen comparison.
3. **Execute** — an isolated in-memory SQLite simulator injects a lost acknowledgment after commit and runs a deterministic bounded-retry actor.
4. **Verify** — a private state oracle counts external effects, independently of the actor's success report.
5. **Export** — CrashLab can produce a failing regression assertion, check a narrowly scoped synthetic deduplication correction, and render a portable HTML failure replay.

## Reproducibility and privacy

- `stateproof/crashlab.py`: bounded planner and synthetic executor.
- `stateproof/crashlab_eval.py`: frozen-manifest / SHA-256 validation and equal-budget protocol.
- `stateproof/crashlab_regression.py`: executable synthetic regression export.
- `stateproof/crashlab_showcase.py`: replay verification and sanitized standalone HTML.
- `stateproof/crashpilot.py`: earlier separate Muse-as-actor diagnostic pilot, which **correctly recovered** from a lost refund acknowledgment.
- `tests/`: executable unit and integration checks; 200 passed in the Oct 29–30 macOS development run.

Local evidence and frozen challenge contracts reside under `evidence/` and are gitignored. No real payment, customer, deployment, or internal Uber/Google data is used. SHA-256 digests are local change-detection checks; they are **not** independent cryptographic attestations.

## Scope, limitations, and provenance

Commit-boundary fault injection, deterministic validation, idempotency/reconciliation, agent benchmarking, and LLM-based chaos engineering have substantial prior art. CrashLab claims **no invention of these techniques**. Its prototype contribution is the integrated **public-contract → model-selected crash plan → isolated execution → independent effect check → regression/replay** workflow.

The initially committed StateProof baseline preceded these later CrashLab modules. Development evidence, original commits, and limitations are preserved; the project should be judged for the work actually implemented and demonstrated during the event. No unpublished DuraTrace/TRACE work or data is included.

**Do not interpret a deterministic actor's false-success report as a Muse false-success incident.**
