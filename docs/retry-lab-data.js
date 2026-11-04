window.CRASHLAB = {
  "meta": {
    "model": "muse-spark-1.3",
    "response_id": "resp_6aeb460fbf3f54cd3a6f4779",
    "input_tokens": 1150,
    "output_tokens": 1930
  },
  "receipt": "b0891dbd0221917911e82b5c1b366efa40f89b0d6b852bbbb4235db7188cb76e",
  "policy": {
    "action": "retry_same_key",
    "operation_id": "reserve_slot",
    "quote": "replaying the exact same key returns the original reservation without another hold",
    "reason": "Documentation explicitly guarantees idempotency key deduplication prevents another hold, so ambiguous result permits same-key retry."
  },
  "description": "Creates one reservation. A stable reservation_key is an idempotency key: replaying the exact same key returns the original reservation without another hold.",
  "pairResult": {
    "policy_correct": 12,
    "operations": 12,
    "correct_final_state": 18,
    "scenarios": 24,
    "duplicates": 0,
    "incomplete": 6,
    "pairs_both_correct": 6,
    "pairs": 6,
    "controls": {
      "conservative": 0,
      "always_retry": 0,
      "naive_keyword": 0,
      "negation_keyword": 0
    },
    "example": [
      {
        "operation_id": "op_h8f4",
        "reference": "verify_then_escalate",
        "muse_action": "verify_then_escalate",
        "muse_quote": "the message is sent and billed a second time",
        "correct": true,
        "pair_name": "webhook_deliver"
      },
      {
        "operation_id": "op_r2b6",
        "reference": "retry_same_key",
        "muse_action": "retry_same_key",
        "muse_quote": "without sending or billing the message a second time",
        "correct": true,
        "pair_name": "webhook_deliver"
      }
    ]
  },
  "redis": {
    "schema": "stateproof-redis-streams-v1",
    "engine": "Redis",
    "version": "8.6.0",
    "created_utc": "2026-11-04T18:12:07.855735+00:00",
    "reference": "https://redis.io/docs/latest/develop/data-types/streams/idempotency/",
    "method": "The server accepted the first append. A separate connection checked XLEN before the producer closed its socket without reading the reply. After an immediate retry, a separate connection queried XRANGE.",
    "scope": "Disposable loopback server; synthetic shipment intents; no model call; no persistence, failover process, window expiration or downstream delivery was measured.",
    "cases": [
      {
        "id": "plain",
        "title": "Business ID in the message body",
        "first_command": [
          "XADD",
          "crashlab-plain",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "retry_command": [
          "XADD",
          "crashlab-plain",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "observed_before_retry": 1,
        "retry_reply": "1793815927760-0",
        "entries": [
          {
            "stream_id": "1793815927758-0",
            "fields": {
              "shipment": "shipment-1042",
              "attempt": "1"
            }
          },
          {
            "stream_id": "1793815927760-0",
            "fields": {
              "shipment": "shipment-1042",
              "attempt": "1"
            }
          }
        ],
        "entry_count": 2
      },
      {
        "id": "explicit",
        "title": "Same producer and idempotent ID",
        "first_command": [
          "XADD",
          "crashlab-explicit",
          "IDMP",
          "producer-A",
          "shipment-1042",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "retry_command": [
          "XADD",
          "crashlab-explicit",
          "IDMP",
          "producer-A",
          "shipment-1042",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "observed_before_retry": 1,
        "retry_reply": "1793815927769-0",
        "entries": [
          {
            "stream_id": "1793815927769-0",
            "fields": {
              "shipment": "shipment-1042",
              "attempt": "1"
            }
          }
        ],
        "entry_count": 1
      },
      {
        "id": "producer",
        "title": "Producer changes during failover",
        "first_command": [
          "XADD",
          "crashlab-producer",
          "IDMP",
          "producer-A",
          "shipment-1042",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "retry_command": [
          "XADD",
          "crashlab-producer",
          "IDMP",
          "producer-B",
          "shipment-1042",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "observed_before_retry": 1,
        "retry_reply": "1793815927780-1",
        "entries": [
          {
            "stream_id": "1793815927780-0",
            "fields": {
              "shipment": "shipment-1042",
              "attempt": "1"
            }
          },
          {
            "stream_id": "1793815927780-1",
            "fields": {
              "shipment": "shipment-1042",
              "attempt": "1"
            }
          }
        ],
        "entry_count": 2
      },
      {
        "id": "auto",
        "title": "Same producer and identical contents",
        "first_command": [
          "XADD",
          "crashlab-auto",
          "IDMPAUTO",
          "producer-A",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "retry_command": [
          "XADD",
          "crashlab-auto",
          "IDMPAUTO",
          "producer-A",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "observed_before_retry": 1,
        "retry_reply": "1793815927790-0",
        "entries": [
          {
            "stream_id": "1793815927790-0",
            "fields": {
              "shipment": "shipment-1042",
              "attempt": "1"
            }
          }
        ],
        "entry_count": 1
      },
      {
        "id": "auto_content",
        "title": "Retry changes the attempt field",
        "first_command": [
          "XADD",
          "crashlab-auto_content",
          "IDMPAUTO",
          "producer-A",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "retry_command": [
          "XADD",
          "crashlab-auto_content",
          "IDMPAUTO",
          "producer-A",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "2"
        ],
        "observed_before_retry": 1,
        "retry_reply": "1793815927799-0",
        "entries": [
          {
            "stream_id": "1793815927797-0",
            "fields": {
              "shipment": "shipment-1042",
              "attempt": "1"
            }
          },
          {
            "stream_id": "1793815927799-0",
            "fields": {
              "shipment": "shipment-1042",
              "attempt": "2"
            }
          }
        ],
        "entry_count": 2
      },
      {
        "id": "explicit_content",
        "title": "Explicit ID survives a changed attempt field",
        "first_command": [
          "XADD",
          "crashlab-explicit_content",
          "IDMP",
          "producer-A",
          "shipment-1042",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "1"
        ],
        "retry_command": [
          "XADD",
          "crashlab-explicit_content",
          "IDMP",
          "producer-A",
          "shipment-1042",
          "*",
          "shipment",
          "shipment-1042",
          "attempt",
          "2"
        ],
        "observed_before_retry": 1,
        "retry_reply": "1793815927801-0",
        "entries": [
          {
            "stream_id": "1793815927801-0",
            "fields": {
              "shipment": "shipment-1042",
              "attempt": "1"
            }
          }
        ],
        "entry_count": 1
      }
    ],
    "sha256": "cc7555fd3b360677bbe00cb886d4f22e0e09bc467aae3251c788f73f232ccbb3"
  },
  "table": "CREATE TABLE reservations (id INTEGER PRIMARY KEY, intent_id TEXT NOT NULL, request_key TEXT, attempt_no INTEGER NOT NULL)",
  "insert": "INSERT INTO reservations(intent_id, request_key, attempt_no) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
  "read": "SELECT id, intent_id, request_key, attempt_no FROM reservations ORDER BY id",
  "intent": "BOOK-1042",
  "key": "req-1042",
  "indexPattern": "^\\s*CREATE\\s+(?:UNIQUE\\s+)?INDEX\\s+[a-z_][a-z0-9_]*\\s+ON\\s+reservations\\s*\\(\\s*(?:request_key|intent_id|attempt_no)(?:\\s*,\\s*(?:request_key|intent_id|attempt_no)){0,2}\\s*\\)\\s*;?\\s*$",
  "defaultCase": {
    "index_sql": "CREATE UNIQUE INDEX retry_key ON reservations(request_key, attempt_no)",
    "fault": "after",
    "key": "forward",
    "policy": "retry_same_key"
  },
  "template": "\"\"\"Reproduce a StateProof booking retry in SQLite. Run this file with Python 3.\"\"\"\nimport json\nimport re\nimport sqlite3\nimport unittest\nfrom contextlib import closing\n\n# The browser export replaces only the following assignment with your selected case.\nCASE = {\"index_sql\": \"CREATE UNIQUE INDEX retry_key ON reservations(request_key, attempt_no)\", \"fault\": \"after\", \"key\": \"forward\", \"policy\": \"retry_same_key\"}  # EXPORTED_CASE\n\nCREATE_TABLE = \"CREATE TABLE reservations (id INTEGER PRIMARY KEY, intent_id TEXT NOT NULL, request_key TEXT, attempt_no INTEGER NOT NULL)\"\nINSERT = \"INSERT INTO reservations(intent_id, request_key, attempt_no) VALUES (?, ?, ?) ON CONFLICT DO NOTHING\"\nREAD = \"SELECT id, intent_id, request_key, attempt_no FROM reservations ORDER BY id\"\nINTENT = \"BOOK-1042\"\nREQUEST_KEY = \"req-1042\"\nCOLUMN = r\"(?:request_key|intent_id|attempt_no)\"\nINDEX_PATTERN = rf\"^\\s*CREATE\\s+(?:UNIQUE\\s+)?INDEX\\s+[a-z_][a-z0-9_]*\\s+ON\\s+reservations\\s*\\(\\s*{COLUMN}(?:\\s*,\\s*{COLUMN}){{0,2}}\\s*\\)\\s*;?\\s*$\"\n\n\ndef database(index_sql):\n    if len(index_sql) > 300 or re.fullmatch(INDEX_PATTERN, index_sql, re.I | re.ASCII) is None:\n        raise ValueError('Enter one CREATE [UNIQUE] INDEX on request_key, intent_id or attempt_no.')\n    db = sqlite3.connect(':memory:', isolation_level=None)\n    try:\n        db.execute(CREATE_TABLE)\n        db.execute(index_sql)\n    except Exception:\n        db.close()\n        raise\n    return db\n\n\ndef attempt(db, case, number):\n    key = REQUEST_KEY if case['key'] == 'forward' else None\n    db.execute(INSERT, (INTENT, key, number))\n\n\ndef probe(case):\n    with closing(database(case['index_sql'])) as disposable:\n        attempt(disposable, case, 1)\n        attempt(disposable, case, 2)\n        return len(disposable.execute(READ).fetchall())\n\n\ndef run_case(case, verify):\n    if case['fault'] not in ('before', 'after') or case['key'] not in ('forward', 'drop') or case['policy'] not in ('retry_same_key', 'verify_then_escalate'):\n        raise ValueError('Unsupported fault, key binding or policy')\n    permitted = case['policy'] == 'retry_same_key'\n    if verify and permitted:\n        permitted = probe(case) == 1\n    with closing(database(case['index_sql'])) as db:\n        if case['fault'] == 'after':\n            attempt(db, case, 1)\n        # The caller receives no acknowledgement under either injected fault.\n        if permitted:\n            attempt(db, case, 2)\n        return db.execute(READ).fetchall()\n\n\nclass BookingRetryRegression(unittest.TestCase):\n    def assert_one_booking(self, verify):\n        rows = run_case(CASE, verify)\n        self.assertEqual(len(rows), 1, f'Expected 1 reservation for {INTENT}; SQLite returned {len(rows)}. Rows: {rows}')\n\n    def test_recorded_policy(self):\n        self.assert_one_booking(verify=False)\n\n    def test_policy_with_probe(self):\n        self.assert_one_booking(verify=True)\n\n\nif __name__ == '__main__':\n    unittest.main(verbosity=2)\n",
  "templateLine": "CASE = {\"index_sql\": \"CREATE UNIQUE INDEX retry_key ON reservations(request_key, attempt_no)\", \"fault\": \"after\", \"key\": \"forward\", \"policy\": \"retry_same_key\"}  # EXPORTED_CASE"
};
