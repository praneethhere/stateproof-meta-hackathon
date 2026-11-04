"""Replay the four-write intent witness on isolated upstream Redis and NATS servers."""

from __future__ import annotations
import argparse
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from stateproof.crashlab import digest
from stateproof.intent_study import commands, expected_rows, passes
from stateproof.redis_stream_probe import call, encode, isolated_server

MODES = ("tenant_scoped", "global_key", "global_key_attempt")


def identity(row, mode):
    tenant, _, key, _, attempt = row
    if mode == "tenant_scoped":
        return tenant, key
    if mode == "global_key":
        return "global", key
    if mode == "global_key_attempt":
        return "global", f"{key}-{attempt}"
    raise ValueError("Unsupported client ID mapping")


def body(row):
    tenant, intent, _, payload, attempt = row
    return {
        "tenant": tenant,
        "local_intent": intent,
        "payload": payload,
        "attempt_no": str(attempt),
    }


def result(mode, trace, entries):
    expected = expected_rows(commands("AABC"))
    actual = sorted(
        (e["body"]["tenant"], e["body"]["local_intent"], e["body"]["payload"])
        for e in entries
    )
    return {
        "mapping": mode,
        "writes": trace,
        "entries": entries,
        "observed_business_rows": actual,
        "expected": expected,
        "count_pass": passes(expected, actual, "count"),
        "identity_multiset_pass": passes(expected, actual, "identity_multiset"),
    }


def redis_cases(binary):
    cases = []
    with isolated_server(binary) as (address, version):
        for mode in MODES:
            stream = "intent-" + mode
            trace = []
            for i, row in enumerate(commands("AABC")):
                producer, iid = identity(row, mode)
                fields = body(row)
                cmd = [
                    "XADD",
                    stream,
                    "IDMP",
                    producer,
                    iid,
                    "*",
                    *(word for pair in fields.items() for word in pair),
                ]
                if i == 0:
                    with socket.create_connection(address, timeout=3) as sender:
                        sender.sendall(encode(cmd))
                        deadline = time.monotonic() + 3
                        while call(address, "XLEN", stream) != 1:
                            if time.monotonic() > deadline:
                                raise RuntimeError(
                                    "First Redis append was not observed"
                                )
                            time.sleep(0.005)
                    ack = "discarded_after_independent_observation"
                else:
                    ack = call(address, *cmd)
                trace.append(
                    {
                        "producer": producer,
                        "idempotent_id": iid,
                        "body": fields,
                        "ack": ack,
                    }
                )
            final = call(address, "XRANGE", stream, "-", "+")
            entries = [
                {"server_seq": sid, "body": dict(zip(fields[::2], fields[1::2]))}
                for sid, fields in final
            ]
            cases.append(result(mode, trace, entries))
    return {
        "engine": "Redis Streams",
        "server_version": version,
        "oracle": "XRANGE on a new connection",
        "cases": cases,
    }


@contextmanager
def nats_server(binary):
    with tempfile.TemporaryDirectory(prefix="stateproof-nats-") as dirname:
        work = Path(dirname)
        log = work / "nats.log"
        with log.open("w") as output:
            proc = subprocess.Popen(
                [
                    str(binary),
                    "--addr",
                    "127.0.0.1",
                    "--port",
                    "-1",
                    "--jetstream",
                    "--store_dir",
                    str(work / "data"),
                    "--ports_file_dir",
                    str(work),
                ],
                stdout=output,
                stderr=output,
            )
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and proc.poll() is None:
                    ports = list(work.glob(f"*_{proc.pid}.ports"))
                    if ports:
                        try:
                            endpoint = json.loads(ports[0].read_text())["nats"][0]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            time.sleep(0.02)
                            continue
                        if urlsplit(endpoint).hostname != "127.0.0.1":
                            raise RuntimeError(
                                "Expected a private loopback NATS endpoint"
                            )
                        break
                    time.sleep(0.02)
                else:
                    raise RuntimeError(
                        "Private NATS server failed to start: " + log.read_text()[-350:]
                    )
                yield endpoint
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()


async def measure_nats(endpoint):
    import importlib.metadata
    import nats
    from nats.js.api import StorageType, StreamConfig

    producer = await nats.connect(endpoint, allow_reconnect=False, connect_timeout=3)
    try:
        observer = await nats.connect(
            endpoint, allow_reconnect=False, connect_timeout=3
        )
        try:
            sender = producer.jetstream()
            reader = observer.jetstream()
            cases = []
            for mode in MODES:
                stream = "SP_" + mode.upper()
                subject = "stateproof." + mode
                await sender.add_stream(
                    config=StreamConfig(
                        name=stream,
                        subjects=[subject],
                        storage=StorageType.MEMORY,
                        duplicate_window=60.0,
                    )
                )
                trace = []
                for i, row in enumerate(commands("AABC")):
                    p, iid = identity(row, mode)
                    message_id = p + "/" + iid
                    fields = body(row)
                    payload = json.dumps(fields, sort_keys=True).encode()
                    headers = {"Nats-Msg-Id": message_id}
                    if i == 0:
                        # No subscription consumes the JetStream PubAck sent to this reply inbox.
                        await producer.publish(
                            subject,
                            payload,
                            reply=producer.new_inbox(),
                            headers=headers,
                        )
                        await producer.flush(timeout=3)
                        deadline = time.monotonic() + 3
                        while (await reader.stream_info(stream)).state.messages != 1:
                            if time.monotonic() > deadline:
                                raise RuntimeError("First NATS append was not observed")
                            await asyncio.sleep(0.005)
                        ack = "unobserved_reply_inbox_after_independent_observation"
                    else:
                        reply = await sender.publish(
                            subject, payload, headers=headers, timeout=3
                        )
                        ack = {"seq": reply.seq, "duplicate": bool(reply.duplicate)}
                    trace.append(
                        {"Nats-Msg-Id": message_id, "body": fields, "ack": ack}
                    )
                info = await reader.stream_info(stream)
                entries = []
                for seq in range(info.state.first_seq, info.state.last_seq + 1):
                    msg = await reader.get_msg(stream, seq=seq)
                    entries.append({"server_seq": seq, "body": json.loads(msg.data)})
                if len(entries) != info.state.messages:
                    raise ValueError("NATS stream count and retrieval disagree")
                cases.append(result(mode, trace, entries))
            return {
                "engine": "NATS JetStream",
                "server_version": str(producer.connected_server_version),
                "client_version": importlib.metadata.version("nats-py"),
                "oracle": "stream_info and get_msg on a separate connection",
                "duplicate_window_seconds": 60,
                "cases": cases,
            }
        finally:
            await observer.close()
    finally:
        await producer.close()


def run(redis, nats):
    first = redis_cases(redis)
    with nats_server(nats) as endpoint:
        second = asyncio.run(measure_nats(endpoint))
    record = {
        "schema": "stateproof-cross-broker-intent-witness-v1",
        "schedule": "AABC",
        "engines": [first, second],
        "method": "One private server per engine, one fresh stream per mapping, sequential immediate sends. A separate connection observes the first append; the producer does not consume its application acknowledgement. Then the remaining three commands are issued.",
        "scope": "Author-chosen client key mappings with synthetic business intents; in-memory, single server, no network partition, public service, failover, expiry or durable disk recovery.",
    }
    record["sha256"] = digest(record)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--redis", required=True, type=Path)
    p.add_argument("--nats", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    if a.out.exists():
        p.error("Choose a new output file")
    result = run(str(a.redis.resolve()), a.nats.resolve())
    with a.out.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    for r in result["engines"]:
        print(
            r["engine"],
            r["server_version"],
            [
                (
                    c["mapping"],
                    len(c["entries"]),
                    c["count_pass"],
                    c["identity_multiset_pass"],
                )
                for c in r["cases"]
            ],
        )


if __name__ == "__main__":
    main()
