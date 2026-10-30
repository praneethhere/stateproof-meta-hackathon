# StateProof Lab — Can we prove an AI agent's success claim?

**Meta Global AI Developer Hackathon 2026 | Indie Developer | Push the Frontier**

StateProof Lab is a local, synthetic demonstration of evidence-gated AI-agent outcome verification. An agent may report success even when a payment, refund, or software deployment did not reach the intended external state. StateProof uses **Meta Muse Spark 1.3** to choose independent read-only evidence probes and submit a proposed verdict. A separate deterministic evidence gate accepts only conclusions supported by the observations.

**What this project demonstrates:** model-directed investigation, bounded tool execution, `VERIFIED` / `FAILED` / `INCONCLUSIVE` outcomes, explicit handling of unavailable readbacks, and comparison against non-LLM baselines. It is **not** a production payment, deployment, or security system.

## Features

- **Interactive local studio:** select a synthetic order, rollout, or refund case, then inspect the agent's claim, readbacks, model tool decisions, and evidence-backed verdict.
- **Live Meta mode:** Muse Spark 1.3 calls allowlisted `inspect_evidence` and `submit_verdict` functions; the Python runner enforces argument checks, probe budgets, and tool-call limits.
- **Independent verification:** the verdict is checked against a separate rule-based gate, not accepted merely because Muse says it is correct.
- **Offline negative control:** deliberately submit an unsupported `VERIFIED` verdict with inadequate evidence and watch the gate reject it. **This injected verdict is not a mistake made by Muse.**
- **Comparison:** same-case contract-aware, cheap-first, and seeded-random deterministic baselines, including evidence-acquisition cost.
- **Reproducible synthetic receipts:** local JSON observations with a SHA-256 change-detection chain. This is **not** a signed or externally authenticated audit log.

## Run locally

Tested on macOS using Python 3.14. Other Python versions and platforms have not yet been independently validated.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q tests
python -m stateproof.m25_studio
```

Open **http://127.0.0.1:8765/index.html**. Choose a scenario, select **Replay deterministic gate (free)** or **Challenge the evidence gate (free)**. Neither uses the Meta API.

### Optional: live Meta investigation

Configure `MODEL_API_KEY` locally. Never place a key in Git or send it to another person. With a valid Meta Model API account and available credits:

```bash
read -s MODEL_API_KEY
export MODEL_API_KEY
STATEPROOF_ENABLE_META=1 python -m stateproof.m25_studio --max-live 1
```

Open the same local address and click **Investigate with Meta Muse**. A live request consumes API credits and can incur charges after promotional credits are exhausted. `--max-live` restricts attempts in the current server session only; **it is not an account-level spending cap**, and restarting the server resets it.

The studio binds to `127.0.0.1` and runs entirely on synthetic data. No real transactions, refunds, or production deployments are performed.

## Reproducible demo sequence

1. Choose a **rollout** case where the simulated agent claims the deployment succeeded.
2. Run the **offline negative control**: the gate rejects `VERIFIED` when a CI success flag is the only evidence.
3. Run an **offline replay**: an independent `runtime_revision` readback reveals that production remains on `r1` even though the contract requires `r2`.
4. Optionally run the **live Muse investigation**: show the model choosing a readback and submitting a verdict; compare the result with the deterministic baselines.

For clean and unavailable-readback examples, an `INCONCLUSIVE` result can be the appropriate evidence-grounded outcome.

## What has been verified, and what has not

- **Verified in the development environment:** 146 automated tests passed; the local UI rendered; a live Muse Spark investigation selected `runtime_revision` and returned an evidence-supported `FAILED` verdict on a known synthetic deployment case; the independent offline negative control rejected an unsupported candidate.
- **Not established:** superiority to strong deterministic baselines, production reliability, performance on unfamiliar real-world workflows, or methodological novelty. The contract-aware baseline reaches the same verdict at the same evidence cost in the demonstrated rollout case.
- **Evaluation scope:** small, known synthetic examples; this is not yet a blinded external benchmark. Any demonstrated pilot examples should be distinguished from held-out testing.

## Implementation and provenance

The project was developed during the October 2026 hackathon period. The October 26 feasibility harness is explicitly identified in source files; the later evidence gate, investigator, UI, and negative-control demo were developed subsequently. The public Git history is a checkpoint of the assembled prototype, not evidence that every component was authored at its commit timestamp.

Main modules: `stateproof/evidence_game.py` (synthetic service and probes), `stateproof/m24_runner.py` (Muse investigator and execution controls), `stateproof/evidence_gate.py` (deterministic gate), `stateproof/m25_studio.py` (local studio), `stateproof/m26_negative_control.py` (offline control).

## Safety and limitations

Use only synthetic examples and approved read-only tools. Do not commit API credentials or real customer information. The model chooses evidence under a budget; the independent gate establishes what the observed evidence supports. This system is an educational/experimental prototype and does not attest the correctness or authorization of real transactions.
