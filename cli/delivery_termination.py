"""Cancel and abandon a chartered v8 attempt, keeping its uncertainty sealed (ADR 0019)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

import process_identity
from claude_edit_worker import MAX_TRACE_BYTES
from delivery_control import run_lock
from delivery_projection import lead_claim_active
from delivery_recovery import (ATTEMPT_DIR_UNSAFE, ATTEMPT_NOT_STARTED, LEAD_GUARD_LEDGER_UNREADABLE,
                               OWNER_GENERATION_STALE, RecoveryRefused, build_recovery_block, recovery_eligibility)
from execution_contracts import ContractError, canonical, envelope_digest, validate_receipt
from execution_ledger import ExecutionLedger, utc_now
from fsutil import repo_root

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


def _attempt_paths(root: Path | None, work_id: str, attempt_id: str) -> tuple[Path, Path, Path]:
    project_root = (root or repo_root()).resolve()
    if (not isinstance(work_id, str) or not work_id or any(part in {"", ".", ".."} for part in work_id.split("/"))
            or "/" in work_id or not isinstance(attempt_id, str) or not attempt_id
            or any(char not in "0123456789abcdef" for char in attempt_id)):
        raise ContractError("work id or attempt id is invalid")
    run_dir = project_root / ".flow" / "runs" / work_id
    execution_dir = run_dir / "execution"
    ledger_path = execution_dir / "ledger.sqlite"
    if ledger_path.is_symlink() or not ledger_path.is_file() or execution_dir.is_symlink():
        raise RecoveryRefused(LEAD_GUARD_LEDGER_UNREADABLE, "the delivery ledger is absent or unsafe")
    attempt_dir = execution_dir / attempt_id
    if attempt_dir.is_symlink() or not attempt_dir.is_dir():
        raise RecoveryRefused(ATTEMPT_DIR_UNSAFE, "the attempt directory is absent or a symlink")
    return run_dir, attempt_dir, ledger_path


def _read_snapshot(ledger_path: Path, attempt_id: str) -> dict[str, Any]:
    try:
        snapshot = ExecutionLedger(ledger_path, read_only=True).snapshot(attempt_id)
    except (sqlite3.Error, ContractError, OSError, ValueError) as exc:
        raise RecoveryRefused(LEAD_GUARD_LEDGER_UNREADABLE, str(exc)) from None
    if snapshot["execution_protocol_version"] != 8:
        raise ContractError("cancel and abandon apply to protocol v8 attempts only")
    return snapshot


def _check_started(snapshot: dict[str, Any], expected_generation: int) -> None:
    if snapshot["status"] != "started":
        raise RecoveryRefused(ATTEMPT_NOT_STARTED, f"attempt is {snapshot['status']}")
    if snapshot["owner_generation"] != expected_generation:
        raise RecoveryRefused(OWNER_GENERATION_STALE, f"current owner generation is {snapshot['owner_generation']}")


def abandon_cause(snapshot: dict[str, Any]) -> str:
    """Why the attempt stopped, from the ledger: a pending expansion, else its latest interruption."""
    if any(item.get("status") == "pending" for item in snapshot.get("expansions", [])):
        return "expansion_paused"
    interruptions = snapshot.get("interruptions", [])
    return interruptions[-1]["cause"] if interruptions else "unmarked_process_exit"


def abandon_delivery(work_id: str, attempt_id: str, *, actor: str, explanation: str, expected_generation: int,
                     root: Path | None = None) -> dict[str, Any]:
    """Seal a stuck started v8 attempt as abandoned after reaping its recorded process groups.

    Fences mirror a lead change (ADR 0016 order): the run lock, a
    non-blocking claim of the attempt's recovery lock held until the seal (a
    live run refuses as ``attempt_running``, a recovery or decision as
    ``recovery_in_progress``), then the send lock and the ledger transaction.
    It works whatever the lead status is and never changes the lead claim.
    """
    if type(expected_generation) is not int:
        raise ContractError("expected generation is required")
    run_dir, attempt_dir, ledger_path = _attempt_paths(root, work_id, attempt_id)
    ledger = ExecutionLedger(ledger_path)
    with run_lock(run_dir), ledger.recovery_lock(attempt_id, holder="recovery"):
        snapshot = _read_snapshot(ledger_path, attempt_id)
        if snapshot["envelope"]["work_id"] != work_id:
            raise ContractError("attempt belongs to another run")
        _check_started(snapshot, expected_generation)
        reaped = process_identity.reap(attempt_dir)
        cause = abandon_cause(snapshot)
        with ledger.send_lock():
            sealed = ledger.seal_terminal_uncertain(
                attempt_id, "abandoned", expected_generation=expected_generation, actor=actor,
                explanation=explanation, cause=cause, receipt_path=attempt_dir / "receipt.json",
                build_receipt=terminal_receipt_renderer(snapshot["envelope"], attempt_dir, status="abandoned",
                                                        actor=actor, explanation=explanation, cause=cause))
    return {**sealed, "work_id": work_id, "cause": cause, "reaped": reaped}


def control_view(attempt_dir: Path, ledger: ExecutionLedger, attempt_id: str) -> dict[str, Any]:
    """Who, if anyone, is running the attempt: control records first, the lock probe as corroboration."""
    found = process_identity.records(attempt_dir)
    latest = found[-1] if found else None
    parent = process_identity.parent_live(latest) if latest else "unrecorded"
    return {"parent": parent, "live": parent == "live", "lock": ledger.probe_recovery_lock(attempt_id),
            "cancel_supported": bool(latest and latest.get("cancel_supported")),
            "records": [{"owner_generation": item["owner_generation"], "pid": item.get("pid"),
                         "closed": item["closed"], "verdict": process_identity.parent_live(item),
                         "groups": [{"pgid": group["pgid"], "kind": group["kind"],
                                     "alive": process_identity.group_alive(group)} for group in item["groups"]]}
                        for item in found]}


def next_command(work_id: str, snapshot: dict[str, Any], control: dict[str, Any], *, lead_active: bool) -> str | None:
    """The single command that moves a started v8 attempt forward, or None once it is terminal."""
    if snapshot["status"] != "started":
        return None
    attempt_id, generation = snapshot["attempt_id"], snapshot["owner_generation"]
    stop = f"--actor NAME --explanation TEXT --expected-generation {generation}"
    if control["live"]:
        return f"flow run cancel-delivery {work_id} {attempt_id} {stop}"
    if control["lock"] == "held":
        # A recovery or decision holds the fence with no live dispatching parent.
        return f"flow run inspect-delivery {work_id} --attempt-id {attempt_id}"
    pending = [item["request_id"] for item in snapshot.get("expansions", []) if item.get("status") == "pending"]
    if pending:
        return (f"flow run decide-expansion {work_id} {attempt_id} {pending[0]} --approve|--deny "
                f"--expected-generation {generation} --actor NAME --explanation TEXT")
    if recovery_eligibility(snapshot["envelope"], snapshot, lead_active=lead_active)["recoverable"]:
        return f"flow run recover-delivery-lead {work_id} {attempt_id}"
    return f"flow run abandon-delivery {work_id} {attempt_id} {stop}"


def stuck_attempts(root: Path | None = None) -> list[dict[str, Any]]:
    """Every started v8 attempt in the project, each with its single next command. Read-only."""
    project_root = (root or repo_root()).resolve()
    runs_dir = project_root / ".flow" / "runs"
    found: list[dict[str, Any]] = []
    if runs_dir.is_symlink() or not runs_dir.is_dir():
        return found
    for run_dir in sorted(runs_dir.iterdir()):
        ledger_path = run_dir / "execution" / "ledger.sqlite"
        if run_dir.is_symlink() or ledger_path.is_symlink() or not ledger_path.is_file():
            continue
        try:
            delivery = json.loads((run_dir / "run.json").read_text()).get("delivery")
        except (OSError, json.JSONDecodeError, AttributeError):
            delivery = None
        try:
            ledger = ExecutionLedger(ledger_path, read_only=True)
            with sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True) as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
                # A ledger that predates the protocol column holds no v8 attempt.
                ids = [row[0] for row in db.execute("SELECT attempt_id FROM attempts WHERE status='started' "
                                                    "AND execution_protocol_version=8 ORDER BY rowid")
                       ] if "execution_protocol_version" in columns else []
            snapshots = [ledger.snapshot(attempt_id) for attempt_id in ids]
        except (sqlite3.Error, ContractError, OSError, ValueError) as exc:
            found.append({"work_id": run_dir.name, "attempt_id": None, "error": f"ledger unreadable: {exc}"})
            continue
        for snapshot in snapshots:
            attempt_dir = run_dir / "execution" / snapshot["attempt_id"]
            control = control_view(attempt_dir, ledger, snapshot["attempt_id"])
            active = lead_claim_active(delivery, snapshot["envelope"])
            rows = snapshot["actions"] + snapshot["manager_calls"]
            found.append({
                "work_id": snapshot["work_id"], "attempt_id": snapshot["attempt_id"],
                "owner_generation": snapshot["owner_generation"], "live": control["live"],
                "parent": control["parent"], "lock": control["lock"],
                "lead_status": (delivery or {}).get("owner_status"),
                "uncertain": {"started": sum(item["status"] == "started" for item in rows),
                              "unknown": sum(item["status"] == "unknown" for item in rows)},
                "open_expansion": next((item["request_id"] for item in snapshot.get("expansions", [])
                                        if item.get("status") == "pending"), None),
                "next_command": next_command(snapshot["work_id"], snapshot, control, lead_active=active)})
    return found
