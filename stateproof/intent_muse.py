"""One frozen Muse Spark test-design call, followed by offline SQLite grading."""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess

from stateproof.crashlab import digest, MODEL
from stateproof.intent_study import grade_plan, ROOT, READOUTS

MESSAGE = """Design one black-box release test for a multi-tenant booking service. Each distinct (tenant, local booking ID) must end with exactly one stored copy of its specified payload. Repeating a logical booking must preserve that outcome. IDs and request keys are chosen locally by each tenant, so a request key or local booking ID may also occur at another tenant. In this instance the payload is identical for all four named bookings. Attempts increment per logical booking; all other fields stay fixed on its retries.

Available logical requests are A=(north, booking 1, key k7), B=(north, booking 2, key k9), C=(south, booking 1, key k7), D=(south, booking 2, key k9). The implementation starts empty. Its inserts ignore uniqueness conflicts. It may have one UNIQUE index over an unknown nonempty subset of (tenant, local booking ID, request key, payload, attempt number), or no uniqueness index. You cannot read the schema. Choose one fixed schedule of one to four appends (the labels A through D, in order, with repetition allowed), followed by one final readout. The readouts available are total row count; set of (tenant, local booking ID, payload) ignoring multiplicity; or multiset of those tuples preserving multiplicity. Each readout compares observed state with the correct business state for your schedule.

Your objective is to accept correct implementations and detect as many incorrect implementations as possible using the fewest writes. Return the tool call with the schedule, chosen readout and a short reason. Do not claim an executed result."""
TOOL = {
    "type": "function",
    "name": "propose_booking_test",
    "description": "Propose a non-executing bounded test plan.",
    "parameters": {
        "type": "object",
        "properties": {
            "schedule": {
                "type": "string",
                "description": "One to four letters from ABCD",
            },
            "readout": {"type": "string", "enum": list(READOUTS)},
            "reason": {
                "type": "string",
                "description": "Brief explanation of what the plan tests",
            },
        },
        "required": ["schedule", "readout", "reason"],
        "additionalProperties": False,
    },
}
FROZEN = (
    "INTENT_STUDY_PROTOCOL.md",
    "stateproof/intent_muse.py",
    "stateproof/intent_study.py",
    "research/verify_intent.py",
    "docs/intent-study-evidence.json",
)
SCHEMA = "stateproof-muse-test-design-v1"


def parse_proposal(raw):
    proposal = json.loads(raw)
    if not isinstance(proposal, dict) or set(proposal) != {
        "schedule",
        "readout",
        "reason",
    }:
        raise ValueError("Invalid proposal fields")
    seq, mode, reason = proposal["schedule"], proposal["readout"], proposal["reason"]
    if (
        not isinstance(seq, str)
        or not re.fullmatch("[ABCD]{1,4}", seq)
        or mode not in READOUTS
    ):
        raise ValueError("Invalid schedule or readout")
    if not isinstance(reason, str) or not 1 <= len(reason) <= 2000:
        raise ValueError("Invalid rationale")
    return proposal


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_freeze():
    head = git("rev-parse", "HEAD")
    git("ls-files", "--error-unmatch", "--", *FROZEN)
    if git("status", "--porcelain", "--", *FROZEN):
        raise RuntimeError("Frozen experiment files differ from the committed revision")
    remote = git("ls-remote", "origin", "refs/heads/main").split()
    if len(remote) != 2 or remote[0] != head:
        raise RuntimeError(
            "Publish this exact HEAD to origin/main before the first model request"
        )
    return head


def score_proposal(proposal):
    chosen = grade_plan(proposal["schedule"], proposal["readout"])
    same_trace = grade_plan(proposal["schedule"], "identity_multiset")
    return {
        k: chosen[k]
        for k in (
            "schedule",
            "readout",
            "writes",
            "correctly_classified",
            "false_approvals",
            "false_refusals",
        )
    } | {
        "adapters": len(chosen["adapters"]),
        "same_trace_with_multiset_correct": same_trace["correctly_classified"],
    }


def publish_observation(out, meta, raw=None):
    if raw is not None:
        try:
            proposal = parse_proposal(raw)
            meta["proposal"] = proposal
        except (TypeError, ValueError) as exc:
            meta["failure_stage"] = "parse_response"
            meta["failure_class"] = type(exc).__name__
        else:
            meta["score"] = score_proposal(proposal)
            meta["status"] = "scored"
    record = {**meta, "sha256": digest(meta)}
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )
    tmp.replace(out)
    return record


def run_first():
    out = ROOT / "docs/intent-muse.json"
    previous = json.loads(out.read_text())
    if previous.get("schema") != SCHEMA or previous.get("status") not in (
        "not_run",
        "scored",
        "unscored",
    ):
        raise RuntimeError("Unexpected public receipt")
    if previous["status"] != "not_run":
        if previous.get("sha256") != digest(
            {k: v for k, v in previous.items() if k != "sha256"}
        ):
            raise RuntimeError(
                "Previously saved first-attempt receipt has a bad checksum"
            )
        return previous
    private = ROOT / "evidence" / "intent-test-design"
    private.mkdir(parents=True, exist_ok=True)
    arrived = private / "first-observation.json"
    if arrived.is_file():
        observation = json.loads(arrived.read_text())
        return publish_observation(out, observation["meta"], observation["raw"])
    marker = private / "first-attempt.json"
    if marker.exists():
        raise RuntimeError(
            "First attempt already started without a complete local observation. No new model call has been made."
        )
    if not os.getenv("MODEL_API_KEY"):
        raise RuntimeError(
            "Set MODEL_API_KEY locally before requesting the single paid model call"
        )
    from openai import OpenAI

    head = verify_freeze()
    client = OpenAI(
        base_url="https://api.meta.ai/v1",
        api_key=os.environ["MODEL_API_KEY"],
        max_retries=0,
        timeout=90,
    )
    meta = {
        "schema": SCHEMA,
        "status": "unscored",
        "model": MODEL,
        "frozen_git_commit": head,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model_request_number": 1,
        "request_sha256": digest(
            {
                "input": MESSAGE,
                "tools": [TOOL],
                "model": MODEL,
                "reasoning": "high",
                "max_output_tokens": 5000,
            }
        ),
        "protocol_sha256": hashlib.sha256((ROOT / FROZEN[0]).read_bytes()).hexdigest(),
    }
    with marker.open("x", encoding="utf8") as handle:
        json.dump(meta, handle, indent=2)
    stage = "model_request"
    raw = None
    try:
        response = client.responses.create(
            model=MODEL,
            input=MESSAGE,
            tools=[TOOL],
            tool_choice="auto",
            parallel_tool_calls=False,
            reasoning={"effort": "high"},
            max_output_tokens=5000,
        )
        meta["response_id"] = getattr(response, "id", None)
        meta["usage"] = {
            k: getattr(getattr(response, "usage", None), k, None)
            for k in ("input_tokens", "output_tokens")
        }
        stage = "parse_response"
        calls = [
            i for i in response.output if getattr(i, "type", None) == "function_call"
        ]
        if (
            not str(meta["response_id"]).startswith("resp_")
            or len(calls) != 1
            or calls[0].name != TOOL["name"]
        ):
            raise ValueError("Expected one identified tool proposal")
        arguments = calls[0].arguments
        if not isinstance(arguments, str) or len(arguments) > 12000:
            raise ValueError("Unexpected proposal length")
        raw = arguments
    except Exception as exc:
        meta["failure_stage"] = stage
        meta["failure_class"] = type(exc).__name__
        meta["http_status"] = getattr(exc, "status_code", None)
    # Save the first observation before grading. Recovery never contacts Meta.
    tmp = arrived.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"meta": meta, "raw": raw}, ensure_ascii=False), encoding="utf8"
    )
    tmp.replace(arrived)
    return publish_observation(out, meta, raw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument("--accept-api-cost", action="store_true")
    a = p.parse_args()
    if not (a.live and a.accept_api_cost):
        p.error("The single Meta call requires --live --accept-api-cost")
    record = run_first()
    print(
        json.dumps(
            {
                k: record.get(k)
                for k in (
                    "status",
                    "response_id",
                    "proposal",
                    "score",
                    "failure_stage",
                    "failure_class",
                )
                if k in record
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
