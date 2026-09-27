"""Cancel and abandon a chartered v8 attempt, keeping its uncertainty sealed (ADR 0019)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from claude_edit_worker import MAX_TRACE_BYTES
from delivery_recovery import build_recovery_block
from execution_contracts import canonical, envelope_digest, validate_receipt
from execution_ledger import utc_now

# The receipt validator's own bound on either trace (execution_contracts).
MAX_SEALED_TRACE_BYTES = MAX_TRACE_BYTES
TRACE_FILES = ("claude-implementer.debug.log", "claude-implementer.events.ndjson")
TRACE_FIELDS = {"claude-implementer.debug.log": "diagnostic_trace", "claude-implementer.events.ndjson": "event_trace"}


def _regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def build_terminal_receipt(envelope: dict[str, Any], attempt_dir: Path, snapshot: dict[str, Any],
                           blocks: dict[str, Any], *, status: str, termination: dict[str, Any]) -> dict[str, Any]:
    """Render a cancelled or abandoned receipt from one ledger snapshot and the envelope.

    Pure apart from reading attempt files: it makes no ledger or lock call,
    runs no test, and never touches the worktree. Evidence Flow can no longer
    read is recorded as null with an ``evidence_damage`` entry instead of
    refusing, so a damaged attempt can still be sealed.
    """
    damage: list[dict[str, Any]] = []
    baseline_path = attempt_dir / "baseline.json"
    try:
        baseline = json.loads(baseline_path.read_text()) if _regular_file(baseline_path) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        baseline = None
    if not isinstance(baseline, dict):
        baseline = None
        damage.append({"kind": "baseline_missing"})
    evidence: dict[str, Any] = {"source_commit": envelope["source_commit"], "worktree": envelope["worktree"],
                                "allowed_paths": envelope["allowed_paths"], "baseline": baseline,
                                "edit": None, "tests": None, "verifier_input_sha256": None}
    for name in TRACE_FILES:
        path = attempt_dir / name
        if not _regular_file(path):
            continue
        data = path.read_bytes()
        record = {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        if len(data) > MAX_SEALED_TRACE_BYTES:
            damage.append({"kind": "trace_oversized", **record})
        else:
            evidence[TRACE_FIELDS[name]] = record
    draft = attempt_dir / "receipt.json"
    replaced = hashlib.sha256(draft.read_bytes()).hexdigest() if _regular_file(draft) else None
    if replaced is not None:
        damage.append({"kind": "draft_receipt_replaced", "sha256": replaced})
    receipt: dict[str, Any] = {
        "schema_version": 1, "execution_protocol_version": envelope["execution_protocol_version"],
        "work_id": envelope["work_id"], "attempt_id": envelope["attempt_id"],
        "envelope_digest": envelope_digest(envelope), "charter_digest": envelope["charter_digest"],
        "manifest_digest": envelope["manifest_digest"], "charter_sources": envelope["charter_sources"],
        "run_protocol_revision": 2, "roster": envelope["roster"], "status": status, "reason": termination["cause"],
        "manager_calls": snapshot["manager_calls"], "actions": snapshot["actions"], "replans": snapshot["replans"],
        "checkpoints": snapshot.get("magentic_checkpoints", []), "failure_detail": "",
        "evidence": evidence, "created_at": utc_now(),
        "verifier_inputs": snapshot.get("verifier_inputs", []),
        "verifier_evaluations": snapshot.get("verifier_evaluations", []),
        "verifier_usage": snapshot["verifier_usage"],
    }
    for key in ("lineage_usage", "expansion", "manager_progress"):
        if blocks.get(key) is not None:
            receipt[key] = blocks[key]
    if snapshot.get("recoveries"):
        receipt["recovery"] = build_recovery_block(snapshot, replaced_draft_sha256=replaced)
    receipt.update({field: envelope[field] for field in ("shaper_contract_digest", "delivery_charter_digest",
                                                          "handoff_digest", "delivery_lead_claim_digest",
                                                          "delivery_lead_claim")})
    receipt["termination"] = {"actor": termination["actor"], "explanation": termination["explanation"],
                              "cause": termination["cause"], "owner_generation": snapshot["owner_generation"],
                              "lead_generation": envelope["delivery_lead_claim"]["generation"]}
    receipt["evidence_damage"] = damage
    return receipt


def terminal_receipt_renderer(envelope: dict[str, Any], attempt_dir: Path, *, status: str, actor: str,
                              explanation: str, cause: str) -> Callable[[dict[str, Any], dict[str, Any]], bytes]:
    """The ``build_receipt`` callback a terminal seal runs inside its transaction."""
    def render(snapshot: dict[str, Any], blocks: dict[str, Any]) -> bytes:
        receipt = build_terminal_receipt(envelope, attempt_dir, snapshot, blocks, status=status,
                                         termination={"actor": actor, "explanation": explanation, "cause": cause})
        validate_receipt(envelope, receipt)
        return (canonical(receipt) + "\n").encode()
    return render
