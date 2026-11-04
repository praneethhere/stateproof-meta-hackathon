# StateProof CrashLab — paste-ready submission fields

**Team Name:** StateProof CrashLab  
**Track:** Indie Developer  
**Problem statement:** Push the Frontier  
**Public repository:** https://github.com/praneethhere/stateproof-meta-hackathon  
**Video:** Add the actual public or unlisted YouTube URL after upload; no placeholder.  
**Optional X viral-track URL:** Leave blank unless entering that separate prize.

> Status: This text is truthful for the existing public experiments. It deliberately does not assert a successful new Muse policy run or a completed new HTML page. If that run succeeds, add its actual evidence and numbers, not guessed data.

## Project description

**StateProof CrashLab — crash-testing AI agents at the commit boundary.**

AI agents increasingly change external state through credits, bookings, and dispatch operations. When a write commits but its response is lost, an agent cannot safely assume that a retry is harmless. Even a verification read can be stale.

CrashLab is an inspectable testing environment for that failure. Meta Muse Spark 1.3 reads unfamiliar synthetic API descriptions and proposes consequential fault locations. A separate Muse tool-using execution was tested against a real loopback HTTP service backed by SQLite. CrashLab deliberately dropped a post-commit reply, returned a stale ledger read, and used an independent SQLite oracle to check what actually happened.

In one recorded episode, Muse checked the ledger, received stale evidence, retried the credit, and produced **two committed effects for one intended operation**. It subsequently reported FAILED. A separate deterministic counterfactual replay blocked the recorded second write at the tool boundary, preserving one effect; the model's continuation after denial was **not observed**. CrashLab also shows the cost of a hard stop: a genuine pre-commit failure can leave the task incomplete.

The public project includes two interactive evidence viewers, reproducible synthetic HTTP experiments, source code and tests. Earlier exploratory StateProof Lab work is excluded from the submitted tree and disclosed in `PROVENANCE.md` with original Git history preserved. The project uses established retry and fault-injection ideas; it does not claim universal exactly-once behavior or a new research protocol.

## Describe how you used Meta products

We used **Muse Spark 1.3 through Meta Model API** for two genuine model behaviors. First, Muse reads the public documentation of a synthetic workflow and proposes an allowlisted crash plan: the operation, failure boundary, hypothesis, and relevant readback. Second, Muse operates an isolated loopback HTTP service using `perform_operation`, `inspect_ledger`, and `report_outcome` tool calls, enabling us to observe actual recovery choices under deliberately ambiguous external state.

The deterministic harness—not Muse—injects faults, checks SQLite, and enforces retry authorization. The model never sees the private committed-state oracle. A new separate experimental extension also allows Muse to **propose**, but not authorize, per-operation retry policies from documentation. That extension should only be described as *evaluated with Muse* if the paid model call actually completed and its result was checked.

## Why Meta's models matter

A conventional test harness can inject a known HTTP failure, but it does not automatically interpret unfamiliar business operations or show how a genuine LLM agent reacts to ambiguous evidence. Muse gives CrashLab an agent to evaluate and a semantic fault-planning component. The saved Muse episode illustrates how a model can reason from the information available to it yet still issue a consequential duplicate when the readback is stale.

The infrastructure is intentionally model-agnostic and the guard is deterministic: we do **not** claim Meta alone can provide the protection. The project tests Muse's role in contract interpretation and recovery behavior, while keeping the final safety authority outside any language model. Two small synthetic planning cases are demonstrations, not evidence of general model superiority.

## Biggest obstacle

We needed to distinguish what an agent **believed** from what the external system **committed**. That required a fault-injecting HTTP service, separate SQLite verification, explicit evidence types, and reproducible saved records. Model API 503 persistence errors and a 400 interrupted the original multi-condition run, so the runner now journals interruptions and checkpoints a clearly labeled follow-up instead of counting incomplete API attempts as model failures. A later live guard continuation also encountered a 503, which is why the public guarded result is a post-hoc replay, not a fresh Muse continuation.

## Compared with other models

Muse Spark 1.3 provided useful contract-level reasoning and tool calls for the synthetic workflows. In a recorded stale-read recovery episode, a second write committed and Muse later reported failure. We **have not** conducted a controlled same-task comparison against other frontier models, so we cannot reliably rank its performance against them. Our evaluation is small and deliberately limited.

## Partner technology feedback

We called Meta Model API directly and did not evaluate Fireworks, Modal, or Baseten in this submission. We cannot provide firsthand feedback on their performance.

## Additional selection questions

- **What matters most?** Tool-call fidelity, correct handling of uncertain outcomes, reliable APIs, independently verifiable results, model reasoning quality, cost, and latency.
- **Hardest part of switching?** Different structured tool-call schemas, prompt contracts, error handling, response continuity, and the cost of reproducing reliability evaluations.
- **Production blocker?** Operational reliability, bounded error recovery, observable tool traces, known provider idempotency guarantees, and cost/availability commitments.
- **Likelihood/opinion/recommendation ratings:** Select your own genuine assessment. No score is supplied by the project artifacts.
- **Recommend Muse Code:** Mark Not used / N/A if offered; we have no confirmed use of Muse Code on this project.

## Completion checklist

- [ ] Cleanup patch applied and new code tests pass.
- [ ] New protocol committed **before** optional live Muse policy run.
- [ ] If live model succeeds, verify `docs/policy.html` and `docs/policy-evidence.json`, and do not claim the deterministic policy eval was a live Muse actor run.
- [ ] New public commit pushed; CI passes; Pages links render from a signed-out browser.
- [ ] Three-minute YouTube video uploaded, duration and permissions tested.
- [ ] Submission description reflects the **final** code, not planned features.
- [ ] Submit using the portal, verify the actual confirmation, before Nov 4 at 9 PM Eastern.
