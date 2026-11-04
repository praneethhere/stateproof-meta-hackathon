# Three-minute StateProof CrashLab demonstration — production plan

**Deadline:** Wednesday, November 4, 2026, 9 PM Eastern / 8 PM Central. Aim to submit by 6 PM Central with a working public YouTube link.

## Non-negotiable labels

- **RECORDED MUSE ACTOR · OCT 30:** original episode from `docs/recovery.html` (Muse made a second write after a stale zero; independently observed 2 effects, then reported FAILED).
- **POST-HOC DETERMINISTIC REPLAY:** retry-boundary replay of Muse's recorded tool prefix; guard stopped second HTTP write, but there was **no new Muse continuation**.
- **LOCAL DETERMINISTIC CONTROL:** one-write limit after a precommit failure leaves 0 effects. Not a Meta model run.
- **RECORDED META POLICY CALL · NOV 2/3:** only if the new `crashlab_policy --strategy muse` call actually succeeds; the policy is Muse-generated, the evaluator is deterministic. Show the actual response ID and contract-quoted policy text, not a fabricated response.

## Shot list (target 2:55)

| Time | Screen | Narration purpose |
| --- | --- | --- |
| 0:00–0:22 | Recovery public page — observed 2/1, then the step where observed stale count = 0 but actual = 1. Label RECORDED MUSE ACTOR. | Hook: an agent checked, but the read was stale; a second write committed. |
| 0:22–0:44 | Draw simple pipeline: Muse / adapter / local HTTP / SQLite / independent oracle. | Who sees which evidence; SQLite oracle is not exposed to model. |
| 0:44–1:14 | Play RECORDED Muse steps: write → dropped reply → stale read → retry → two effects → FAILED. | Show actual sequence and outcome; not false DONE. |
| 1:14–1:43 | Switch to POST-HOC DETERMINISTIC REPLAY. | Boundary rejects recorded second write, 1 effect; no continuation claimed. |
| 1:43–2:01 | Hard-stop precommit control, 0/1. | Hard stop protects safety but sacrifices completion. |
| 2:01–2:33 | If live policy run succeeded: policy.html with quoted semantics and 14 real local HTTP test results. Otherwise show original planner's two *synthetic* challenge examples with careful small-n label. | Model is useful for proposing a per-operation policy, **not proof of server guarantees**. |
| 2:33–2:52 | Terminal: new policy CLI test + `pytest` green + commit + GitHub code. | Reproducibility and eligibility provenance. |
| 2:52–2:55 | URLs and final one-line value proposition. | Clear next action. |

## Narration (conditional policy segment in brackets; approximately 355 words)

When an AI agent calls an API and loses the reply, it faces a question: did the write fail—or did it commit?

This is StateProof CrashLab, a synthetic testing environment for exactly that uncertainty.

In one recorded Muse Spark 1.3 episode, the agent was asked to post a customer credit once. It inspected the ledger, saw zero, and sent the write. Our local HTTP service committed the transaction to SQLite—but deliberately dropped the acknowledgment.

The next ledger read was stale and still reported zero. Muse requested the credit again. The independent database now held two effects for one intended operation. The model eventually rechecked and reported FAILED. That was an unsafe external action, **not a false-success claim**.

CrashLab separates the agent's observations from ground truth. A local HTTP fault injector controls the reply, while the independent SQLite oracle counts committed effects. No real payments or customer data are involved.

Next, we replayed the recorded tool sequence through a deterministic authorization boundary. When the second write was requested, the boundary blocked it before HTTP, leaving one effect. This is a **counterfactual replay**, not a live Muse continuation after denial.

There is a price. If the first request actually fails before committing, a blanket retry stop may leave the task incomplete. Our tests show zero effects instead of one.

[IF ACTUAL META POLICY RUN IS AVAILABLE: So we also ask Muse to read an unfamiliar synthetic API contract and propose a policy for each operation—retry with the same key only where documented, otherwise verify and escalate. The model's proposal does not grant permission. A trusted adapter enforces the server's verified deduplication behavior, while a deterministic client executes fourteen real local HTTP and SQLite fault checks. Here is the recorded policy and its exact outcome, alongside offline controls.]

[IF NO META POLICY RUN: Muse also examines unfamiliar API descriptions and proposes a crash location. We tested two synthetic challenge workflows. These are examples, not a statistical benchmark or a claim of a new reliability protocol.]

The public repository includes reproducible tests, interactive evidence viewers, the independent oracle, the experimental protocol, and an explicit provenance record.

StateProof CrashLab: test what actually committed—before trusting an agent's next action.

## Recording and publishing

1. Record 1920×1080 or 1280×720 in macOS Screenshot (`Shift` + `Cmd` + `5`), zoom browser text until legible.
2. Label every clip with exact evidence type. Never use LIVE on a saved run, and label time-compressed footage.
3. Keep final video at **three minutes or less**; verify duration using Finder/QuickTime.
4. Upload to YouTube as **Unlisted** or **Public**, not Private; verify the link in a signed-out/incognito window.
5. Verify the repo is publicly accessible, Pages demos load, the final commit passed CI, and the portal actually shows submission confirmation.
