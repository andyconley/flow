"""Turn a v8 attempt into a pre-release one (no sealed token budget) by direct SQL (ADR 0020, I6).

``create_attempt`` now refuses such an envelope, so tests that prove
pre-release attempts stay readable and abandonable build them this way.
"""

import copy
import json
import sqlite3
from pathlib import Path

TOKEN_KEYS = ("max_lineage_tokens", "token_tranche", "unobserved_send_tokens")


def legacy_envelope(envelope):
    legacy = copy.deepcopy(envelope)
    for key in TOKEN_KEYS:
        legacy["limits"].pop(key, None)
    legacy.get("expansion_headroom", {}).pop("tokens", None)
    if "expansion_headroom" in legacy and not legacy["expansion_headroom"]:
        legacy.pop("expansion_headroom")
    return legacy


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def insert_legacy_attempt(ledger_path: Path, attempt_dir: Path, template: dict, attempt_id: str,
                          predecessor: dict | None = None) -> dict:
    """Insert a started pre-release v8 attempt directly, as one sealed before this release would sit in the ledger."""
    envelope = legacy_envelope(template)
    envelope["attempt_id"] = attempt_id
    envelope["checkpoint_dir"] = str(attempt_dir / "checkpoints")
    envelope.pop("predecessors", None)
    if predecessor is not None:
        envelope["predecessors"] = [predecessor]
    attempt_dir.mkdir(parents=True, exist_ok=True)
    (attempt_dir / "checkpoints").mkdir(exist_ok=True)
    (attempt_dir / "envelope.json").write_text(_canonical(envelope) + "\n")
    with sqlite3.connect(ledger_path) as db:
        db.execute("INSERT INTO attempts(attempt_id,work_id,envelope_json,status,reason,receipt_path,recovery_version,"
                   "owner_generation,owner_actor,execution_protocol_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (attempt_id, envelope["work_id"], _canonical(envelope), "started", "", None, 2,
                    envelope["delivery_lead_claim"]["generation"], envelope["delivery_lead_claim"]["lead_id"], 8))
        db.execute("INSERT INTO events(at,attempt_id,action_id,event,detail) VALUES(?,?,?,?,?)",
                   ("2026-09-27T00:00:00+00:00", attempt_id, None, "attempt_started", ""))
    return envelope
