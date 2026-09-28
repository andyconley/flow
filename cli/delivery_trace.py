"""``flow run trace``: the per-call correlation chain of a v8 attempt and its lineage (ADR 0020).

Read-only. The ledger is read in one transaction through ``lineage_view``;
control records and manager request files are read without writing. The
banner for a stuck attempt names why it is stuck and the next command, which
is the same one ``flow run stuck`` gives.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import manager_requests
import process_identity
from delivery_projection import lead_claim_active
from delivery_termination import control_view, next_command
from execution_contracts import ContractError, digest
from execution_ledger import ExecutionLedger
from fsutil import repo_root

TRACE_SCHEMA_VERSION = 1
PAID_PROVIDERS = {"codex", "claude"}
# The event that starts a send, and the one that observes its response, per row kind.
SEND_START = {"manager_call": "manager_send_started", "producer": "worker_dispatched", "verifier": "verifier_send_claimed"}
OBSERVED = {"manager_call": "manager_response_observed", "producer": "response_observed", "verifier": "response_observed"}


class TraceError(Exception):
    """The run, the attempt, or its ledger cannot be read."""


def _seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 3)
    except ValueError:
        return None


def _grant_history(events: list[dict[str, Any]], row_id: str) -> list[dict[str, Any]]:
    history = []
    for event in events:
        if event["event"] == "grant_changed" and event["action_id"] == row_id:
            try:
                detail = json.loads(event["detail"])
            except (TypeError, json.JSONDecodeError):
                continue
            history.append({"seq": event["seq"], "op": detail.get("op"), "grant_id": detail.get("grant_id"),
                            "owner_generation": detail.get("owner_generation"), "reason": detail.get("reason")})
    return history


def _first(events: list[dict[str, Any]], row_id: str, name: str) -> dict[str, Any] | None:
    return next((event for event in events if event["action_id"] == row_id and event["event"] == name), None)


def _request_file(attempt_dir: Path, call: dict[str, Any]) -> dict[str, Any]:
    path = f"{manager_requests.REQUEST_DIR}/{call['call_id']}.json"
    try:
        data = manager_requests.read_request_file(attempt_dir, call["call_id"])
    except ContractError as exc:
        return {"path": path, "present": False, "digest_matches": False, "error": str(exc)}
    if data is None:
        return {"path": path, "present": False, "digest_matches": False}
    try:
        stored = json.loads(data)
        matches = (stored.get("call_id") == call["call_id"]
                   and stored.get("prompt_digest") == call["request"]["prompt_digest"]
                   and digest(stored.get("messages")) == call["request"]["prompt_digest"])
    except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
        matches = False
    return {"path": path, "present": True, "digest_matches": matches}


def _row(kind: str, item: dict[str, Any], snapshot: dict[str, Any], attempt_dir: Path,
         groups: dict[str, list[int]], links: dict[str, dict[str, Any]]) -> dict[str, Any]:
    events = snapshot["events"]
    envelope = snapshot["envelope"]
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    if kind == "manager_call":
        row_id, request = item["call_id"], item["request"]
        provider, model = envelope["manager"].get("provider", "claude"), envelope["manager"].get("model")
        detail = {"sequence": request["sequence"], "phase": request["phase"], "manager_round": request["manager_round"]}
        timing_kind = "manager_call"
    else:
        row_id, request = item["action_id"], item["request"]
        provider, model = request.get("provider"), request.get("model")
        verifier = request.get("instance_id") in envelope.get("job_contract", {}).get("verifier_instance_ids", [])
        detail = {"sequence": request.get("sequence"), "role": request.get("role"),
                  "instance_id": request.get("instance_id"), "verifier": verifier}
        timing_kind = "verifier" if verifier else "producer"
    started = _first(events, row_id, SEND_START[timing_kind])
    observed = _first(events, row_id, OBSERVED[timing_kind])
    first_seq = min((event["seq"] for event in events if event["action_id"] == row_id), default=None)
    link = links.get(row_id)
    return {
        "type": kind, "row_id": row_id, "seq": first_seq, **detail, "provider": provider, "model": model,
        "status": item["status"], "reason": item.get("reason"),
        "grant_history": _grant_history(events, row_id), "grant_id": item.get("grant_id"),
        "session_id": result.get("session_id") or result.get("thread_id"),
        "input_sha256": result.get("input_sha256"),
        "request_file": _request_file(attempt_dir, item) if kind == "manager_call" else None,
        "pgids": groups.get(row_id, []),
        "checkpoint": ({"checkpoint_id": link["checkpoint_id"], "previous_checkpoint_id": link.get("previous_checkpoint_id")}
                       if link else None),
        "timing": {"send_started_at": started["at"] if started else None,
                   "observed_at": observed["at"] if observed else None,
                   "duration_seconds": _seconds(started["at"] if started else None, observed["at"] if observed else None)},
        "usage": {"raw": result.get("usage")},
    }


def _expansion_entries(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    for event in snapshot["events"]:
        if event["event"] in {"expansion_requested", "expansion_granted", "expansion_decided", "expansion_cancelled",
                              "expansion_grant_consumed", "expansion_grant_lapsed"}:
            try:
                detail = json.loads(event["detail"])
            except (TypeError, json.JSONDecodeError):
                detail = {"grant_id": event["detail"]}
            entries.append({"type": "expansion", "seq": event["seq"], "at": event["at"], "event": event["event"],
                            "row_id": event["action_id"], "detail": detail})
    return entries


def _banner(work_id: str, snapshot: dict[str, Any], control: dict[str, Any] | None, *, lead_active: bool,
            lead_status: str | None) -> dict[str, Any]:
    if snapshot["status"] != "started":
        return {"state": snapshot["status"], "cause": snapshot.get("reason"),
                "receipt_sha256": snapshot.get("sealed_receipt_sha256")}
    events = snapshot["events"]
    pending = next((item for item in snapshot.get("expansions", []) if item.get("status") == "pending"), None)
    rows = snapshot["actions"] + snapshot["manager_calls"]
    uncertain = next((item for item in rows if item["status"] in {"started", "unknown"}), None)
    reason, row_id, since = "interrupted", None, None
    if control and control["live"]:
        reason = "running"
    elif control and control["lock"] == "held":
        reason = "recovery_in_progress"
    elif pending is not None:
        row_id = pending.get("denied_row_id")
        denied = next((item for item in rows if item.get("action_id", item.get("call_id")) == row_id), {})
        reason = f"expansion_paused: {denied.get('reason') or 'limit'}"
        since = next((event for event in events if event["event"] == "expansion_requested"
                      and event["action_id"] == row_id), None)
    elif uncertain is not None:
        row_id = uncertain.get("action_id", uncertain.get("call_id"))
        reason = "reconciliation_required"
        since = next((event for event in reversed(events) if event["action_id"] == row_id), None)
    elif not lead_active:
        reason = f"lead {lead_status or 'inactive'}"
    elif snapshot.get("interruptions"):
        cause = snapshot["interruptions"][-1]
        reason = f"interrupted: {cause['cause']}"
        since = next((event for event in events if event["seq"] == cause.get("ledger_seq")), None)
    if since is None and events:
        since = events[-1]
    return {"state": "started", "reason": reason, "row_id": row_id,
            "since_seq": since["seq"] if since else None, "since_at": since["at"] if since else None,
            "next_command": next_command(work_id, snapshot, control, lead_active=lead_active) if control else None}


def _attempt(work_id: str, run_dir: Path, ledger: ExecutionLedger, entry: dict[str, Any], *, delivery: Any,
             probe: bool) -> dict[str, Any]:
    snapshot = entry["snapshot"]
    attempt_id = entry["attempt_id"]
    if entry["execution_protocol_version"] != 8:
        return {"attempt_id": attempt_id, "execution_protocol_version": entry["execution_protocol_version"],
                "status": entry["status"], "supported": False, "detail": "unsupported_protocol"}
    attempt_dir = run_dir / "execution" / attempt_id
    found = process_identity.records(attempt_dir)
    groups: dict[str, list[int]] = {}
    for record in found:
        for group in record["groups"]:
            if group.get("row_id"):
                groups.setdefault(group["row_id"], []).append(group["pgid"])
    links = {link["pending_id"]: link for link in snapshot.get("magentic_checkpoints", [])}
    rows = ([_row("manager_call", item, snapshot, attempt_dir, groups, links) for item in snapshot["manager_calls"]]
            + [_row("action", item, snapshot, attempt_dir, groups, links) for item in snapshot["actions"]])
    entries = sorted(rows + _expansion_entries(snapshot), key=lambda item: (item["seq"] is None, item["seq"] or 0))
    control = control_view(attempt_dir, ledger, attempt_id) if probe and snapshot["status"] == "started" else None
    lead_active = lead_claim_active(delivery, snapshot["envelope"])
    paid_rows = [item for item in rows if item["provider"] in PAID_PROVIDERS]
    sent = {"started", "completed", "failed", "unknown"}
    return {
        "attempt_id": attempt_id, "execution_protocol_version": 8, "supported": True, "status": snapshot["status"],
        "owner_generation": snapshot.get("owner_generation"), "owner_actor": snapshot.get("owner_actor"),
        "banner": _banner(work_id, snapshot, control, lead_active=lead_active,
                          lead_status=(delivery or {}).get("owner_status") if isinstance(delivery, dict) else None),
        "control_records": [{"owner_generation": item["owner_generation"], "pid": item.get("pid"),
                             "closed": item["closed"], "groups": len(item["groups"])} for item in found],
        "entries": entries,
        "totals": {"paid_calls": sum(item["status"] in sent for item in paid_rows),
                   "verifier_calls": sum(item.get("verifier") is True and item["status"] in sent for item in rows),
                   "unobserved_sends": sum(item["status"] in {"started", "unknown"} for item in paid_rows)},
    }


def trace(work_id: str, attempt_id: str | None = None, *, root: Path | None = None, probe: bool = True) -> dict[str, Any]:
    """The trace view of ``attempt_id`` (default: the latest attempt) and its predecessors."""
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    ledger_path = run_dir / "execution" / "ledger.sqlite"
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise TraceError(f"run not found: {work_id}")
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise TraceError(f"no delivery ledger for {work_id}")
    try:
        delivery = json.loads((run_dir / "run.json").read_text()).get("delivery")
    except (OSError, json.JSONDecodeError, AttributeError):
        delivery = None
    ledger = ExecutionLedger(ledger_path, read_only=True)
    try:
        view = ledger.lineage_view(work_id, attempt_id)
    except ContractError as exc:
        raise TraceError(str(exc)) from exc
    except Exception as exc:  # sqlite3.Error and friends: the ledger is unreadable
        raise TraceError(f"ledger unreadable: {exc}") from exc
    attempts = [_attempt(work_id, run_dir, ledger, entry, delivery=delivery, probe=probe) for entry in view["attempts"]]
    lineage_totals = {key: sum(item.get("totals", {}).get(key, 0) for item in attempts)
                      for key in ("paid_calls", "verifier_calls", "unobserved_sends")}
    return {"schema_version": TRACE_SCHEMA_VERSION, "work_id": work_id, "attempt_id": view["attempt_id"],
            "attempts": attempts, "lineage_totals": lineage_totals}


def render_text(view: dict[str, Any]) -> str:
    """A terminal rendering: the banner of the target attempt first, then each attempt's rows."""
    lines = []
    target = view["attempts"][-1]
    banner = target.get("banner")
    if banner is None:
        lines.append(f"{target['attempt_id']}: {target.get('detail')}")
    elif banner["state"] == "started":
        lines.append(f"STUCK {target['attempt_id']}: {banner['reason']}"
                     + (f" on {banner['row_id'][:12]}" if banner.get("row_id") else "")
                     + (f" since seq {banner['since_seq']} ({banner['since_at']})" if banner.get("since_seq") else ""))
        if banner.get("next_command"):
            lines.append(f"  next: {banner['next_command']}")
    else:
        lines.append(f"{banner['state'].upper()} {target['attempt_id']}: {banner.get('cause') or ''}"
                     f" receipt {str(banner.get('receipt_sha256') or '-')[:16]}")
    for attempt in view["attempts"]:
        lines.append("")
        if not attempt.get("supported"):
            lines.append(f"attempt {attempt['attempt_id']} (v{attempt['execution_protocol_version']}): {attempt['detail']}")
            continue
        lines.append(f"attempt {attempt['attempt_id']} {attempt['status']} generation {attempt['owner_generation']}")
        for entry in attempt["entries"]:
            if entry["type"] == "expansion":
                lines.append(f"  #{entry['seq']:<5} expansion {entry['event']} {json.dumps(entry['detail'], sort_keys=True)}")
                continue
            what = (f"manager {entry['phase']} r{entry['manager_round']}" if entry["type"] == "manager_call"
                    else f"{'verifier' if entry.get('verifier') else 'producer'} {entry.get('role')}")
            grants = " > ".join(f"{item['op']}:{str(item['grant_id'] or '-')[:8]}" for item in entry["grant_history"])
            usage = entry["usage"].get("charged")
            lines.append(f"  #{entry['seq'] if entry['seq'] is not None else '-':<5} {entry['row_id'][:12]} {what} "
                         f"{entry['provider']}/{entry['model']} {entry['status']}"
                         f" {entry['timing']['duration_seconds'] if entry['timing']['duration_seconds'] is not None else '-'}s"
                         + (f" charged {usage}" if usage is not None else "")
                         + (f" session {entry['session_id']}" if entry.get("session_id") else "")
                         + (f" pgid {','.join(map(str, entry['pgids']))}" if entry["pgids"] else "")
                         + (f" grants {grants}" if grants else ""))
        totals = attempt["totals"]
        lines.append("  totals: " + ", ".join(f"{key} {value}" for key, value in totals.items()))
    lines.append("")
    lines.append("lineage: " + ", ".join(f"{key} {value}" for key, value in view["lineage_totals"].items()))
    return "\n".join(lines)
