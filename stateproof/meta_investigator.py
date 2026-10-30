"""Bounded Meta Responses-API investigator. Model never gets arbitrary execution.

Requirements: openai Python SDK and MODEL_API_KEY. API calls incur token usage.
Run --mode fixed or --mode random to avoid all network requests.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .experiments import ExperimentBudget, InvalidExperiment, FAULTS, PROBES, public_prompt

MODEL = "muse-spark-1.3"
BASE_URL = "https://api.meta.ai/v1"
TOOLS = [{
    "type": "function",
    "name": "run_experiment",
    "description": "Run one allowlisted failure-injection experiment against a disposable synthetic order workflow. Returns observable trace and selected read-back; cannot change real state.",
    "parameters": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "fault_id": {"type": "string", "enum": list(FAULTS)},
            "probe_id": {"type": "string", "enum": list(PROBES)},
        },
        "required": ["fault_id", "probe_id"],
    },
}]


def _call_kwargs(*, input_data: Any, previous_response_id: str | None) -> dict:
    args = {
        "model": MODEL, "input": input_data, "tools": TOOLS,
        "tool_choice": "auto", "parallel_tool_calls": False,
        "max_output_tokens": 700, "reasoning": {"effort": "minimal"},
    }
    if previous_response_id:
        args["previous_response_id"] = previous_response_id
    return args


def investigate(target: str, *, budget: int = 2, client: Any = None, max_turns: int = 4) -> dict:
    """Return audit receipt. Client can be injected for deterministic tests.

    Uses server-managed previous_response_id as documented by Meta. No calls
    occur at all until MODEL_API_KEY exists and the function is invoked.
    """
    runner = ExperimentBudget(target, budget)
    if not 1 <= max_turns <= 8:
        raise ValueError("Invalid max_turns")
    if client is None:
        if not os.environ.get("MODEL_API_KEY"):
            raise RuntimeError("MODEL_API_KEY not set; cannot run Meta mode")
        from openai import OpenAI
        client = OpenAI(base_url=BASE_URL, api_key=os.environ["MODEL_API_KEY"], timeout=35, max_retries=0)

    input_data: Any = public_prompt(target, budget)
    previous_id = None
    calls: list[dict] = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    finish_reason = "max_turns"
    final_text = ""
    for turn in range(max_turns):
        response = client.responses.create(**_call_kwargs(input_data=input_data, previous_response_id=previous_id))
        if getattr(response, "status", None) not in ("completed", None):
            finish_reason = "api_" + str(response.status)
            break
        if getattr(response, "usage", None) is not None:
            usage["input_tokens"] += getattr(response.usage, "input_tokens", 0) or 0
            usage["output_tokens"] += getattr(response.usage, "output_tokens", 0) or 0
        function_calls = [item for item in (response.output or []) if getattr(item, "type", None) == "function_call"]
        if not function_calls:
            finish_reason = "model_final_no_tool" if not calls else "model_final"
            final_text = str(getattr(response, "output_text", "") or "")
            break
        pending_outputs = []
        for item in function_calls:
            call_record = {"turn": turn + 1, "tool": getattr(item, "name", None), "call_id": getattr(item, "call_id", None)}
            try:
                if item.name != "run_experiment":
                    raise InvalidExperiment("Tool not on allowlist")
                raw = item.arguments
                if not isinstance(raw, str) or len(raw) > 2048:
                    raise InvalidExperiment("Invalid or oversized argument string")
                parsed = json.loads(raw)
                obs = runner.execute(parsed)
                call_record["arguments"] = parsed
                call_record["accepted"] = True
                tool_result = {"ok": True, "observation": obs, "experiments_remaining": runner.remaining}
            except (ValueError, TypeError) as ex:
                call_record["accepted"] = False
                call_record["error"] = str(ex)
                tool_result = {"ok": False, "error": str(ex), "experiments_remaining": runner.remaining}
            calls.append(call_record)
            pending_outputs.append({"type": "function_call_output", "call_id": item.call_id, "output": json.dumps(tool_result, sort_keys=True)})
        if not runner.remaining:
            # Pair tool calls with outputs even when budget reached; stop in next turn.
            # This final API call lets the model see real executed outcomes.
            response2 = client.responses.create(**_call_kwargs(input_data=pending_outputs, previous_response_id=response.id))
            if getattr(response2, "usage", None) is not None:
                usage["input_tokens"] += getattr(response2.usage, "input_tokens", 0) or 0
                usage["output_tokens"] += getattr(response2.usage, "output_tokens", 0) or 0
            final_text = str(getattr(response2, "output_text", "") or "")
            finish_reason = "budget_exhausted"
            # We deliberately do NOT execute any further function calls.
            break
        input_data = pending_outputs
        previous_id = response.id
    receipt = runner.summary("meta_muse_spark_1.3")
    receipt.update({"tool_calls": calls, "api_usage": usage, "termination": finish_reason, "model_summary": final_text,
                    "verified_model_tool_execution": bool(runner.results),
                    "safety": "synthetic_only; allowlisted_tools; isolated_sqlite; local_oracle_not_sent_to_model"})
    return receipt
