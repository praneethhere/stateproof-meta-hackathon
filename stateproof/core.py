"""Minimal synthetic payment system and independent state verifier.

Everything in this module is simulation: no real payments or external APIs.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass


class LostResponse(Exception):
    """The payment committed, but the simulated client did not receive its reply."""


@dataclass(frozen=True)
class PaymentIntent:
    intent_id: str
    amount_cents: int
    idempotency_key: str


class SimulatedPaymentService:
    def __init__(self, *, enforce_idempotency: bool):
        self.db = sqlite3.connect(":memory:")
        self.db.execute(
            "CREATE TABLE charges ("
            " charge_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " intent_id TEXT NOT NULL, amount_cents INTEGER NOT NULL,"
            " idempotency_key TEXT NOT NULL)"
        )
        self.enforce_idempotency = enforce_idempotency

    def charge(self, intent: PaymentIntent, *, lose_response: bool = False) -> int:
        """Write the charge first; optionally simulate losing the post-commit reply."""
        # The serialized transaction matters: a production idempotency design must
        # make checking/reusing a key atomic with any new external side effect.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.enforce_idempotency:
                existing = self.db.execute(
                    "SELECT charge_id FROM charges WHERE idempotency_key = ?",
                    (intent.idempotency_key,),
                ).fetchone()
                if existing:
                    charge_id = int(existing[0])
                else:
                    cursor = self.db.execute(
                        "INSERT INTO charges (intent_id, amount_cents, idempotency_key)"
                        " VALUES (?, ?, ?)",
                        (intent.intent_id, intent.amount_cents, intent.idempotency_key),
                    )
                    charge_id = int(cursor.lastrowid)
            else:
                cursor = self.db.execute(
                    "INSERT INTO charges (intent_id, amount_cents, idempotency_key)"
                    " VALUES (?, ?, ?)",
                    (intent.intent_id, intent.amount_cents, intent.idempotency_key),
                )
                charge_id = int(cursor.lastrowid)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        if lose_response:
            raise LostResponse("The charge committed, but its response was lost")
        return charge_id

    def charges_for(self, intent_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT charge_id, intent_id, amount_cents, idempotency_key "
            "FROM charges WHERE intent_id = ? ORDER BY charge_id", (intent_id,)
        ).fetchall()
        return [dict(zip(("charge_id", "intent_id", "amount_cents", "idempotency_key"), row)) for row in rows]


def simulated_agent_run(service: SimulatedPaymentService, intent: PaymentIntent) -> dict:
    """A DETERMINISTIC retry client; it is not yet an AI agent."""
    trace = []
    for attempt in (1, 2):
        try:
            charge_id = service.charge(intent, lose_response=(attempt == 1))
            trace.append({"attempt": attempt, "observation": "success", "charge_id": charge_id})
            return {"reported_status": "success", "attempts": trace}
        except LostResponse:
            trace.append({"attempt": attempt, "observation": "timeout_after_commit_unknown_to_client"})
    return {"reported_status": "failed", "attempts": trace}


def independently_verify(service: SimulatedPaymentService, intent: PaymentIntent) -> dict:
    """The oracle reads actual state; it does not trust the client's response."""
    charges = service.charges_for(intent.intent_id)
    total = sum(row["amount_cents"] for row in charges)
    passed = len(charges) == 1 and total == intent.amount_cents
    return {
        "verified": passed,
        "observed_charge_count": len(charges),
        "observed_total_cents": total,
        "expected_charge_count": 1,
        "expected_total_cents": intent.amount_cents,
        "evidence": charges,
    }


def run_case(*, enforce_idempotency: bool) -> dict:
    intent = PaymentIntent(intent_id="SYNTHETIC-ORDER-001", amount_cents=2500,
                           idempotency_key="SYNTHETIC-KEY-001")
    service = SimulatedPaymentService(enforce_idempotency=enforce_idempotency)
    try:
        agent_result = simulated_agent_run(service, intent)
        verification = independently_verify(service, intent)
        return {
            "case": "idempotency_enabled" if enforce_idempotency else "missing_idempotency",
            "intent": asdict(intent),
            "simulated_agent": agent_result,
            "verification": verification,
        }
    finally:
        service.db.close()
