"""M5: Loopback-only HTTP crash laboratory for SYNTHETIC API contracts.

- The service is a real HTTP listener backed by file-based SQLite transactions.
- The first HTTP response can be dropped *after* commit or *before* commit.
- The model only sees bounded tool observations, never the private oracle.
- The runner never follows URLs or executes code found in model/API documents.
- No external business systems or customer data are contacted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from http.client import RemoteDisconnected
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from stateproof.crashlab import (MODEL, canonical, candidate_ids, digest,
                                 load_contract, muse_plan, validate_plan)

INTENT = "SYNTHETIC-INTENT-001"
REQUEST_KEY = "SYNTHETIC-REQUEST-001"
FAULTS = ("after_commit_lost_ack", "before_commit_timeout", "no_fault")
ACTORS = ("retry", "readback", "muse")
READBACK_FAULTS = ("normal", "stale_zero_once", "unavailable")


class LoopbackService:
    """The only HTTP destination is a fresh 127.0.0.1 ephemeral listener."""

    def __init__(self, *, operation: str, dedupe: str, guarded: bool,
                 fault: str, severity: int = 1, readback_fault: str = "normal"):
        if not operation.isidentifier() or len(operation) > 40:
            raise ValueError("Unsafe operation ID")
        if dedupe not in ("request_key", "none") or fault not in FAULTS:
            raise ValueError("Unsupported private implementation or fault")
        if readback_fault not in READBACK_FAULTS:
            raise ValueError("Unsupported readback fault")
        self.operation = operation
        self.dedupe = "request_key" if guarded else dedupe
        self.fault = fault
        self.readback_fault = readback_fault
        self._readback_events: list[dict] = []
        self._post_write_reads = 0
        self.guarded = guarded
        self.severity = severity
        self._lock = Lock()
        self._attempts = 0
        self._events: list[dict] = []
        self._tmp: TemporaryDirectory | None = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None
        self._auth = secrets.token_urlsafe(24)
        self._url: str | None = None

    def __enter__(self):
        self._tmp = TemporaryDirectory(prefix="crashlab-m5-")
        self._db_file = str(Path(self._tmp.name) / "transactions.sqlite3")
        with sqlite3.connect(self._db_file) as con:
            con.execute("CREATE TABLE effects (id INTEGER PRIMARY KEY, operation TEXT NOT NULL, "
                        "intent_id TEXT NOT NULL, request_key TEXT NOT NULL)")
            con.commit()

        outer = self
        class Handler(BaseHTTPRequestHandler):
            server_version = "CrashLabM5/1.0"
            sys_version = ""
            def log_message(self, fmt, *args):
                pass  # No sensitive request lines or tokens in stdout

            def _reply(self, status: int, value: dict):
                payload = canonical(value).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def _allowed(self) -> bool:
                if not secrets.compare_digest(self.headers.get("X-CrashLab-Token", ""), outer._auth):
                    self._reply(403, {"ok": False, "error": "FORBIDDEN"})
                    return False
                return True

            def _drop_ack(self):
                self.close_connection = True
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.connection.close()

            def do_GET(self):
                if not self._allowed():
                    return
                if self.path != "/v1/ledger":
                    self._reply(404, {"ok": False, "error": "UNKNOWN_PATH"})
                    return
                # The external read path may be stale or unavailable even though the
                # independent oracle can inspect committed SQLite rows directly.
                # Do NOT send actual_count or readback fault configuration to the actor.
                with outer._lock:
                    with sqlite3.connect(outer._db_file) as con:
                        actual = con.execute(
                            "SELECT COUNT(*) FROM effects WHERE operation=? AND intent_id=?",
                            (outer.operation, INTENT)).fetchone()[0]
                    is_post_write = outer._attempts > 0
                    if is_post_write:
                        outer._post_write_reads += 1
                    index = outer._post_write_reads
                    if is_post_write and outer.readback_fault == "unavailable":
                        outer._readback_events.append({"post_write_read": index,
                            "actual_count_private": actual, "observed_count": None,
                            "http_status": 503, "condition": "unavailable"})
                        response = (503, {"ok": False, "error": "READBACK_UNAVAILABLE"})
                    elif (is_post_write and outer.readback_fault == "stale_zero_once" and index == 1):
                        outer._readback_events.append({"post_write_read": index,
                            "actual_count_private": actual, "observed_count": 0,
                            "http_status": 200, "condition": "stale_zero_once"})
                        response = (200, {"ok": True, "effect_count": 0,
                                         "expected_count": 1, "intent_id": INTENT})
                    else:
                        outer._readback_events.append({"post_write_read": index if is_post_write else None,
                            "actual_count_private": actual, "observed_count": actual,
                            "http_status": 200, "condition": "normal"})
                        response = (200, {"ok": True, "effect_count": actual,
                                         "expected_count": 1, "intent_id": INTENT})
                self._reply(*response)

            def do_POST(self):
                if not self._allowed():
                    return
                if self.path != "/v1/execute":
                    self._reply(404, {"ok": False, "error": "UNKNOWN_PATH"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= length <= 1024:
                        self._reply(400, {"ok": False, "error": "BAD_LENGTH"})
                        return
                    body = json.loads(self.rfile.read(length))
                except (ValueError, TypeError, UnicodeDecodeError):
                    self._reply(400, {"ok": False, "error": "BAD_JSON"})
                    return
                if (type(body) is not dict or set(body) != {"operation_id", "intent_id", "request_key"}
                    or body["operation_id"] != outer.operation or body["intent_id"] != INTENT
                    or body["request_key"] != REQUEST_KEY):
                    self._reply(400, {"ok": False, "error": "INVALID_SYNTHETIC_REQUEST"})
                    return
                with outer._lock:
                    outer._attempts += 1
                    attempt = outer._attempts
                    if attempt == 1 and outer.fault == "before_commit_timeout":
                        outer._events.append({"attempt": attempt, "phase": "before_commit_timeout",
                                              "committed": False, "response_delivered": False})
                        self._drop_ack()
                        return
                    with sqlite3.connect(outer._db_file, timeout=3) as con:
                        match = con.execute("SELECT id FROM effects WHERE operation=? AND request_key=?",
                                            (outer.operation, REQUEST_KEY)).fetchone()
                        if outer.dedupe == "request_key" and match is not None:
                            committed, deduplicated = False, True
                        else:
                            con.execute("INSERT INTO effects(operation,intent_id,request_key) VALUES(?,?,?)",
                                        (outer.operation, INTENT, REQUEST_KEY))
                            con.commit()
                            committed, deduplicated = True, False
                    if attempt == 1 and outer.fault == "after_commit_lost_ack":
                        outer._events.append({"attempt": attempt, "phase": "after_commit_lost_ack",
                                              "committed": committed, "deduplicated": deduplicated,
                                              "response_delivered": False})
                        self._drop_ack()
                        return
                    outer._events.append({"attempt": attempt, "phase": "ordinary_response",
                                          "committed": committed, "deduplicated": deduplicated,
                                          "response_delivered": True})
                self._reply(200, {"ok": True, "accepted": True, "deduplicated": deduplicated})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._url = f"http://127.0.0.1:{self._server.server_port}"
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)
        if self._tmp:
            self._tmp.cleanup()

    def _send(self, path: str, body: dict | None = None) -> dict:
        if self._url is None:
            raise RuntimeError("HTTP service is not running")
        headers = {"X-CrashLab-Token": self._auth}
        if body is not None:
            headers["Content-Type"] = "application/json"
        # Never accepts a user-supplied URL or arbitrary path.
        req = Request(self._url + path, headers=headers,
                      data=canonical(body).encode() if body is not None else None,
                      method="POST" if body is not None else "GET")
        try:
            with urlopen(req, timeout=3) as response:
                return json.loads(response.read(4096).decode("utf-8"))
        except HTTPError as ex:
            # HTTPError subclasses URLError: handle it first, or a 503 is falsely
            # reported as a network timeout instead of READBACK_UNAVAILABLE.
            if ex.code == 503 and path == "/v1/ledger":
                return {"ok": False, "error": "READBACK_UNAVAILABLE", "status": 503}
            return {"ok": False, "error": "HTTP_ERROR", "status": ex.code}
        except (RemoteDisconnected, ConnectionResetError, BrokenPipeError, TimeoutError,
                socket.timeout, URLError) as ex:
            return {"ok": False, "error": "TIMEOUT_OUTCOME_UNKNOWN",
                    "transport": type(ex).__name__}

    def execute(self) -> dict:
        return self._send("/v1/execute", {"operation_id": self.operation,
                                           "intent_id": INTENT, "request_key": REQUEST_KEY})

    def readback(self) -> dict:
        return self._send("/v1/ledger")

    def oracle(self) -> dict:
        # Independently open the SQLite file, not the HTTP readback or model transcript.
        with sqlite3.connect(self._db_file) as con:
            n = con.execute("SELECT COUNT(*) FROM effects WHERE operation=? AND intent_id=?",
                            (self.operation, INTENT)).fetchone()[0]
        return {"effect_count": n, "expected_count": 1, "correct_state": n == 1,
                "excess_effects": max(0, n - 1), "severity": self.severity}

    @property
    def server_events(self) -> list[dict]:
        return [dict(e) for e in self._events]

    @property
    def readback_events(self) -> list[dict]:
        # Evaluator-only: contains the true SQLite count; never shown to Muse.
        return [dict(e) for e in self._readback_events]

    @property
    def attempts(self) -> int:
        return self._attempts


def deterministic_actor(service: LoopbackService, strategy: str) -> tuple[dict, list[dict], dict]:
    if strategy not in ("retry", "readback"):
        raise ValueError("Invalid actor")
    events = []
    first = service.execute()
    events.append({"tool": "perform_operation", "observation": first})
    current = first
    if not first.get("ok") and strategy == "readback":
        state = service.readback()
        events.append({"tool": "inspect_ledger", "observation": state})
        if state.get("ok") and state["effect_count"] == 1:
            return {"status": "DONE", "reason": "One committed effect observed by HTTP readback."}, events, {"input_tokens": 0, "output_tokens": 0}
        if not state.get("ok") or state["effect_count"] > 1:
            return {"status": "UNKNOWN", "reason": "Could not verify exactly one effect."}, events, {"input_tokens": 0, "output_tokens": 0}
    if not current.get("ok"):
        current = service.execute()
        events.append({"tool": "perform_operation", "observation": current})
    # 'retry' trusts the second successful acknowledgment; 'readback' independently checks it.
    if strategy == "readback":
        state = service.readback()
        events.append({"tool": "inspect_ledger", "observation": state})
        done = bool(state.get("ok") and state["effect_count"] == 1)
        report = {"status": "DONE" if done else "UNKNOWN",
                  "reason": "HTTP readback after retry"}
    else:
        report = {"status": "DONE" if current.get("ok") else "UNKNOWN",
                  "reason": "HTTP acknowledgement received" if current.get("ok") else "No final acknowledgement"}
    return report, events, {"input_tokens": 0, "output_tokens": 0}


AGENT_TOOLS = [
    {"type": "function", "name": "perform_operation", "description": "Perform ONE SYNTHETIC operation by local HTTP; a timeout does not establish whether it committed.",
     "parameters": {"type": "object", "properties": {"intent_id": {"type": "string"}},
                    "required": ["intent_id"], "additionalProperties": False}},
    {"type": "function", "name": "inspect_ledger", "description": "Read a separate synthetic transaction ledger over HTTP; reports committed effect count.",
     "parameters": {"type": "object", "properties": {"intent_id": {"type": "string"}},
                    "required": ["intent_id"], "additionalProperties": False}},
    {"type": "function", "name": "report_outcome", "description": "Finish the task with DONE, FAILED or UNKNOWN and a brief reason. DONE means exactly ONE effect committed.",
     "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": ["DONE", "FAILED", "UNKNOWN"]},
                                                    "reason": {"type": "string"}},
                    "required": ["status", "reason"], "additionalProperties": False}},
]


def _safe_json(raw: Any, required: set[str]) -> dict:
    if not isinstance(raw, str) or len(raw) > 2000:
        raise ValueError("Invalid tool-call payload")
    args = json.loads(raw)
    if type(args) is not dict or set(args) != required:
        raise ValueError("Unexpected function arguments")
    return args


def muse_actor(service: LoopbackService, *, client: Any = None, effort: str = "high",
               max_turns: int = 8, max_calls: int = 10, public_description: str = "") -> tuple[dict | None, list[dict], dict]:
    """Executes actual model-driven, tool-calling HTTP recovery; oracle stays private."""
    if effort not in ("medium", "high", "max") or not 1 <= max_turns <= 10 or not 1 <= max_calls <= 12:
        raise ValueError("Invalid budgets")
    if client is None:
        from openai import OpenAI
        key = os.getenv("MODEL_API_KEY")
        if not key:
            raise RuntimeError("MODEL_API_KEY missing")
        client = OpenAI(base_url="https://api.meta.ai/v1", api_key=key, timeout=65, max_retries=0)
    task = ("Operate a SYNTHETIC local HTTP service. Make exactly ONE business effect of operation "
            f"{service.operation} for intent {INTENT}. The API contract describes it as: "
            + public_description[:1200] + ". An HTTP response might be lost after the server has committed. "
            "Tools allow performing the operation, inspecting the external ledger, and reporting DONE/FAILED/UNKNOWN. "
            "A successful report means exactly one effect, not merely an HTTP 200. "
            "Do not assume that a timeout means success or failure. End by calling report_outcome.")
    previous = None
    model_input: Any = task
    event_log = []
    total = {"input_tokens": 0, "output_tokens": 0}
    report: dict | None = None
    calls = 0
    for turn in range(1, max_turns + 1):
        if calls >= max_calls:
            break
        req = {"model": MODEL, "input": model_input, "tools": AGENT_TOOLS,
               "parallel_tool_calls": False, "tool_choice": "auto", "reasoning": {"effort": effort},
               "max_output_tokens": 1800,
               "instructions": "You are using a synthetic local service. Never claim to have observed outcomes not evidenced by tools. No production actions."}
        if previous is not None:
            req["previous_response_id"] = previous
        answer = client.responses.create(**req)
        usage = getattr(answer, "usage", None)
        total["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
        total["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)
        found = [x for x in (getattr(answer, "output", None) or []) if getattr(x, "type", None) == "function_call"]
        if not found:
            break
        outputs = []
        for f in found:
            if calls >= max_calls:
                break
            calls += 1
            name = getattr(f, "name", "")
            try:
                if name in ("perform_operation", "inspect_ledger"):
                    args = _safe_json(getattr(f, "arguments", ""), {"intent_id"})
                    if args["intent_id"] != INTENT:
                        raise ValueError("Wrong intent")
                    observation = service.execute() if name == "perform_operation" else service.readback()
                elif name == "report_outcome":
                    args = _safe_json(getattr(f, "arguments", ""), {"status", "reason"})
                    if args["status"] not in {"DONE", "FAILED", "UNKNOWN"} or (not isinstance(args["reason"], str) or len(args["reason"]) > 800):
                        raise ValueError("Invalid final report")
                    report = {"status": args["status"], "reason": args["reason"]}
                    observation = {"ok": True, "recorded": True}
                else:
                    raise ValueError("Unknown tool")
                event = {"turn": turn, "tool": name, "accepted": True, "observation": observation}
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                observation = {"ok": False, "error": "INVALID_TOOL_CALL"}
                event = {"turn": turn, "tool": name, "accepted": False}
            event_log.append(event)
            outputs.append({"type": "function_call_output", "call_id": f.call_id,
                            "output": canonical(observation)})
            if report is not None:
                break
        if report is not None:
            break
        previous = answer.id
        model_input = outputs
    return report, event_log, total


def run_http_experiment(data: dict, plan: dict, *, actor: str = "retry", guarded: bool = False,
                        client: Any = None, effort: str = "high",
                        readback_fault: str = "normal") -> dict:
    """One recorded HTTP episode. Does not modify frozen evaluation artifacts."""
    plan = validate_plan(plan, data)
    if actor not in ACTORS:
        raise ValueError("Invalid actor strategy")
    op_id = plan["operation_id"]
    fault = plan["phase"]
    spec = data["private_simulator"][op_id]
    description = next(op["description"] for op in data["public"]["operations"] if op["id"] == op_id)
    with LoopbackService(operation=op_id, dedupe=spec["dedupe"], guarded=guarded,
                         fault=fault, severity=spec["severity"],
                         readback_fault=readback_fault) as svc:
        if actor == "muse":
            report, events, usage = muse_actor(svc, client=client, effort=effort,
                                              public_description=description)
        else:
            report, events, usage = deterministic_actor(svc, actor)
        oracle = svc.oracle()
        raw = {"schema": "stateproof-crashlab-http-m5-v1", "recorded_utc": datetime.now(timezone.utc).isoformat(),
               "execution": "actual_loopback_http_file_sqlite", "synthetic": True,
               "model": MODEL if actor == "muse" else None,
               "actor": actor, "operation_id": op_id, "fault": fault,
               "guarded": guarded, "plan": plan, "public_contract_sha256": digest(data["public"]),
               "actor_report": report, "private_oracle": oracle,
               "false_done": bool(report and report["status"] == "DONE" and not oracle["correct_state"]),
               "attempts": svc.attempts, "actor_events": events,
               "server_events": svc.server_events, "model_usage": usage,
               "limitations": ["Local isolated HTTP and SQLite; not a third-party or production service",
                               "A fixed reference implementation, not arbitrary OpenAPI endpoints",
                               "Server-side commit log is available to the independent evaluator, not the actor",
                               "Model can receive ledger observations only by invoking inspect_ledger"]}
        if readback_fault != "normal":
            raw["schema"] = "stateproof-crashlab-http-m7-v1"
            raw["readback_fault"] = readback_fault
            raw["readback_events_private"] = svc.readback_events
            raw["limitations"].append(
                "Readback disruption is deterministic and configured by the harness; not measured production propagation")
        raw["receipt_sha256"] = digest(raw)
        return raw


def _load_plan(data: dict, receipt_path: Path | None, op: str, fault: str, plan_with_muse: bool, effort: str) -> tuple[dict, dict]:
    if receipt_path is not None:
        saved = json.loads(receipt_path.read_text(encoding="utf-8"))
        plan = saved.get("plan")
        if not isinstance(plan, dict):
            raise ValueError("Receipt does not contain a plan")
        return validate_plan(plan, data), {"origin": "saved_plan", "input_tokens": 0, "output_tokens": 0}
    if plan_with_muse:
        plan, usage = muse_plan(data, effort=effort)
        return plan, {"origin": "live_muse_planner", **usage}
    return validate_plan({"operation_id": op, "phase": fault,
                          "hypothesis": "Check ambiguous transaction boundary in isolated HTTP service.",
                          "readback": "Inspect independent ledger for exactly one effect."}, data), {"origin": "manual", "input_tokens": 0, "output_tokens": 0}


def main() -> None:
    ap = argparse.ArgumentParser(description="CrashLab M5: real loopback HTTP fault execution")
    ap.add_argument("--contract", type=Path, default=Path("contracts/support_credit.json"))
    ap.add_argument("--operation", default="apply_credit")
    ap.add_argument("--fault", choices=FAULTS, default="after_commit_lost_ack")
    ap.add_argument("--plan-receipt", type=Path, help="Reuse an existing saved M1 Muse plan (no planning API call)")
    ap.add_argument("--muse-plan", action="store_true", help="Use Meta API for one new crash plan")
    ap.add_argument("--actor", choices=ACTORS, default="retry")
    ap.add_argument("--guarded", action="store_true", help="Enable simulated request-key deduplication")
    ap.add_argument("--readback-fault", choices=READBACK_FAULTS, default="normal",
                    help="External ledger read condition, after first write; defaults to fully visible")
    ap.add_argument("--live", action="store_true", help="Explicitly allow Meta API calls")
    ap.add_argument("--effort", choices=("medium", "high", "max"), default="high")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if (args.actor == "muse" or args.muse_plan) and not args.live:
        ap.error("Meta calls require explicit --live")
    if args.plan_receipt and args.muse_plan:
        ap.error("Choose either --plan-receipt or --muse-plan")
    if args.live and args.actor != "muse" and not args.muse_plan:
        ap.error("--live supplied but no Muse role selected")
    data = load_contract(args.contract)
    plan, plan_usage = _load_plan(data, args.plan_receipt, args.operation, args.fault,
                                  args.muse_plan, args.effort)
    episode = run_http_experiment(data, plan, actor=args.actor, guarded=args.guarded,
                                  effort=args.effort, readback_fault=args.readback_fault)
    episode["planner_usage"] = plan_usage
    episode["receipt_sha256"] = digest({k: v for k, v in episode.items() if k != "receipt_sha256"})
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(episode, indent=2) + "\n", encoding="utf-8")
    keys = ("actor", "operation_id", "fault", "guarded", "actor_report",
            "private_oracle", "false_done", "attempts", "model_usage", "receipt_sha256")
    preview = {k: episode[k] for k in keys}
    preview["readback_fault"] = args.readback_fault
    print(json.dumps(preview, indent=2))


if __name__ == "__main__":
    main()
