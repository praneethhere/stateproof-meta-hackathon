"""Eligible-window M2.4 investigator: Meta model decisions gated by independent readback.

Important: this demo imports the October 26 prebuild synthetic harness. The M2.4
runner, gate, report and tests are distinct newly authored components.
"""
from __future__ import annotations
import json
import os
from typing import Any
from .evidence_game import Case, Episode, EvidenceError, check_verdict, score, cohort
from .evidence_gate import gate_verdict, proof_chain

TOOLS = [
    {"type": "function", "name": "inspect_evidence",
     "description": "Obtain one independent readback from allowlisted probes, with a budget cost.",
     "parameters": {"type": "object", "properties": {"probe_id": {"type": "string"}},
                    "required": ["probe_id"], "additionalProperties": False}},
    {"type": "function", "name": "submit_verdict",
     "description": "Request a VERIFIED, FAILED, or INCONCLUSIVE conclusion; the evidence gate may reject unsupported claims.",
     "parameters": {"type": "object", "properties": {
         "verdict": {"type": "string", "enum": ["VERIFIED", "FAILED", "INCONCLUSIVE"]},
         "explanation": {"type": "string"}}, "required": ["verdict", "explanation"],
                    "additionalProperties": False}},
]


def _receipt(case: Case, ep: Episode, verdict: str, model_explanation: str,
             termination: str, tool_events: list[dict], api_usage: dict,
             rejected_claims: list[dict], mode: str) -> dict:
    scored = score(ep, verdict)
    public = ep.public_view()
    visible = list(ep.records)
    gated = gate_verdict(public["workflow"], visible)
    scored.update({
        "mode": mode, "case_public": public, "evidence_receipts": visible,
        "receipt_chain": proof_chain(ep.case_id, visible),
        "gate_supported_status": gated, "gate_accepted": verdict == gated,
        "rejected_claims": rejected_claims, "model_explanation": model_explanation,
        "termination": termination, "tool_calls": tool_events, "api_usage": api_usage,
        "note": "Synthetic simulation only. Hidden truth is included in this FINAL evaluator receipt, never in model inputs.",
        "project_component": "M2.4 evidence gate and investigator, authored within Oct 27 build window",
    })
    return scored


def run_offline_gated(case: Case, case_id: str) -> dict:
    ep = Episode(case, case_id)
    try:
        order = {"order": ("charge_count", "fulfillment_count"),
                 "rollout": ("runtime_revision",), "refund": ("settlement_state",)}[case.workflow]
        for probe in order:
            if gate_verdict(case.workflow, ep.records) != "INCONCLUSIVE":
                break
            ep.inspect(probe)
        status = gate_verdict(case.workflow, ep.records)
        return _receipt(case, ep, status, "Deterministic policy demonstration, not a Muse result.",
                        "offline_gate_demo", [], {"input_tokens": 0, "output_tokens": 0}, [], "offline")
    finally:
        ep.close()


def run_muse_gated(case: Case, case_id: str, *, client: Any = None,
                   max_turns: int = 6, max_calls: int = 8) -> dict:
    if type(max_turns) is not int or not 1 <= max_turns <= 10:
        raise ValueError("max_turns must be 1..10")
    if type(max_calls) is not int or not 1 <= max_calls <= 20:
        raise ValueError("max_calls must be 1..20")
    if client is None:
        from openai import OpenAI
        key = os.environ.get("MODEL_API_KEY")
        if not key:
            raise RuntimeError("MODEL_API_KEY not exported")
        client = OpenAI(base_url="https://api.meta.ai/v1", api_key=key,
                        timeout=35.0, max_retries=0)
    ep = Episode(case, case_id)
    previous_id = None
    model_input: Any = json.dumps(ep.public_view(), sort_keys=True)
    events: list[dict] = []
    rejected: list[dict] = []
    token_use = {"input_tokens": 0, "output_tokens": 0}
    claimed, explanation, termination = "INCONCLUSIVE", "No accepted verdict.", "max_turns"
    try:
        for turn in range(1, max_turns + 1):
            if len(events) >= max_calls:
                termination = "call_limit"
                break
            kwargs = {
                "model": "muse-spark-1.3", "input": model_input, "tools": TOOLS,
                "tool_choice": "auto", "parallel_tool_calls": False,
                "reasoning": {"effort": "low"}, "max_output_tokens": 700,
                "instructions": (
                    "You are testing a SYNTHETIC workflow. The agent's success message is not proof. "
                    "Use inspect_evidence for independent observable readbacks. "
                    "Submit a verdict only when supported by observed facts, otherwise INCONCLUSIVE. "
                    "A deterministic contract-based gate checks the evidence; if rejected, acquire a "
                    "better allowable probe if budget remains, or abstain. "
                    "Never assume an unavailable readback proves failure. No real-world actions."
                ),
            }
            if previous_id:
                kwargs["previous_response_id"] = previous_id
            response = client.responses.create(**kwargs)
            usage = getattr(response, "usage", None)
            if usage is not None:
                token_use["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
                token_use["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)
            tool_items = [x for x in (getattr(response, "output", None) or [])
                          if getattr(x, "type", None) == "function_call"]
            if not tool_items:
                termination = "no_tool_call"
                explanation = str(getattr(response, "output_text", "") or "No tool requested")[:1000]
                break
            outputs = []
            accepted = False
            for item in tool_items:
                if len(events) >= max_calls:
                    termination = "call_limit"
                    break
                event = {"turn": turn, "tool": getattr(item, "name", None), "accepted": False}
                try:
                    raw = getattr(item, "arguments", None)
                    if not isinstance(raw, str) or len(raw) > 2000:
                        raise EvidenceError("Invalid argument payload")
                    args = json.loads(raw)
                    if type(args) is not dict:
                        raise EvidenceError("Tool arguments must be object")
                    if item.name == "inspect_evidence":
                        if set(args) != {"probe_id"}:
                            raise EvidenceError("Invalid probe arguments")
                        obs = ep.inspect(args["probe_id"])
                        event["probe"] = args["probe_id"]
                        result = {"ok": True, "observation": obs}
                        event["accepted"] = True
                    elif item.name == "submit_verdict":
                        if set(args) != {"verdict", "explanation"}:
                            raise EvidenceError("Invalid verdict arguments")
                        wanted = check_verdict(args["verdict"])
                        if type(args["explanation"]) is not str or len(args["explanation"]) > 2000:
                            raise EvidenceError("Invalid explanation")
                        gated = gate_verdict(case.workflow, ep.records)
                        if wanted != gated:
                            rejected.append({"requested": wanted, "gate_status": gated, "turn": turn})
                            result = {"ok": False, "error": "Evidence does not support requested verdict.",
                                      "supported_by_current_evidence": gated,
                                      "remaining_budget": ep.remaining}
                            event["error"] = "ungrounded_verdict"
                        else:
                            claimed, explanation = wanted, args["explanation"]
                            result = {"ok": True, "accepted_verdict": wanted}
                            event["accepted"] = True
                            accepted = True
                    else:
                        raise EvidenceError("Tool not allowlisted")
                except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                    event["error"] = str(exc)[:200]
                    result = {"ok": False, "error": str(exc)[:200]}
                events.append(event)
                outputs.append({"type": "function_call_output", "call_id": item.call_id,
                                "output": json.dumps(result, sort_keys=True)})
            if accepted:
                termination = "accepted_verdict"
                break
            if termination == "call_limit":
                break
            model_input = outputs
            previous_id = response.id
        return _receipt(case, ep, claimed, explanation, termination, events, token_use, rejected, "meta")
    finally:
        ep.close()


def run_index(index: int, *, mode: str, client: Any = None) -> dict:
    cases = cohort()
    if type(index) is not int or not 0 <= index < len(cases):
        raise ValueError(f"case-index must be 0..{len(cases)-1}")
    cid, case = cases[index]
    if mode == "offline":
        return run_offline_gated(case, cid)
    if mode == "meta":
        return run_muse_gated(case, cid, client=client)
    raise ValueError("Unknown mode")
