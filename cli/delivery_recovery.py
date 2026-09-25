"""Pure recovery rules for interrupted protocol v8 chartered attempts.

This module decides whether an attempt may be recovered, from which Flow-bound
checkpoint, and which evidence recovery may reuse. It performs no I/O and
grants nothing; the gateway and ledger own every mutation (ADR 0016).
"""

from __future__ import annotations

import json
from typing import Any

from execution_contracts import ContractError

V6_INSPECTION_ONLY = "v6_inspection_only"
V7_NOT_RECOVERABLE = "v7_not_recoverable"
UNSUPPORTED_PROTOCOL = "unsupported_protocol"
ATTEMPT_TERMINAL = "attempt_terminal"
ATTEMPT_RUNNING = "attempt_running"
CONTINUATION_EPOCHS_V5_ONLY = "continuation_epochs_v5_only"
LEAD_GENERATION_INACTIVE = "lead_generation_inactive"
RECOVERY_IN_PROGRESS = "recovery_in_progress"
RECONCILIATION_REQUIRED = "reconciliation_required"
NO_RESTORABLE_CHECKPOINT = "no_restorable_checkpoint"
CHECKPOINT_POSITION_UNRECOVERABLE = "checkpoint_position_unrecoverable"
WORKTREE_DRIFT = "worktree_drift"
EVIDENCE_BINDING_CONFLICT = "evidence_binding_conflict"
ENVELOPE_CHANGED = "envelope_changed"
V8_RESOLUTION_REQUIRES_CHUNK_2 = "v8_resolution_requires_chunk_2"
LEAD_GUARD_LEDGER_UNREADABLE = "lead_guard_ledger_unreadable"
SIBLING_ATTEMPT_NOT_TERMINAL = "sibling_attempt_not_terminal"
PREDECESSOR_LINK_INVALID = "predecessor_link_invalid"
V8_NO_DISPATCH_REGRANT_UNSUPPORTED = "v8_no_dispatch_regrant_unsupported"
WORKTREE_CONTAINS_PROJECT_FLOW = "worktree_contains_project_flow"
OWNER_GENERATION_STALE = "owner_generation_stale"
ITEM_NOT_UNRESOLVED = "item_not_unresolved"
UNRESOLVABLE_ABANDON_ONLY = "unresolvable_abandon_only"
EVIDENCE_INSUFFICIENT = "evidence_insufficient"
EVIDENCE_INVALID = "evidence_invalid"
RESOLUTION_UNBOUND = "resolution_unbound"
V8_EVIDENCE_FILE_REFUSED = "v8_evidence_file_refused"
EXPECTED_GENERATION_REQUIRED = "expected_generation_required"
V8_DISPOSITION_UNSUPPORTED = "v8_disposition_unsupported"
EVIDENCE_FILE_REQUIRED = "evidence_file_required"
EXPECTED_GENERATION_V8_ONLY = "expected_generation_v8_only"

DISPATCH_EVENTS = frozenset({"worker_dispatched", "adapter_send_started"})

EVIDENCE_NEEDED = {
    # Only Flow's stored response observation can resolve an uncertain send
    # (ADR 0012); anything else, including every manager call, is abandon-only.
    "observed_action": "resolve-execution (stored response): resolved_completed with --expected-generation",
    "abandon_only": "unresolvable; abandon only (release, or lifecycle block)",
    NO_RESTORABLE_CHECKPOINT: "none; abandon, or lead supersede and start a successor",
    CHECKPOINT_POSITION_UNRECOVERABLE: "none; abandon, or lead supersede and start a successor",
    LEAD_GENERATION_INACTIVE: "none; attempt fenced",
    RESOLUTION_UNBOUND: "none; the resolution is not bound to this action, attempt, and recovery chain",
}


class RecoveryRefused(ContractError):
    """A stable, reason-coded refusal; ``str()`` starts with the reason code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(reason + (": " + detail if detail else ""))


def _dispatched(snapshot: dict[str, Any], action_id: str) -> bool:
    return any(item["action_id"] == action_id and item["event"] in DISPATCH_EVENTS
               for item in snapshot.get("events", []))


def runtime_outcome(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Return the recorded runtime outcome, or None while the runtime is unfinished."""
    recorded = [item for item in snapshot.get("events", []) if item["event"] == "runtime_outcome_recorded"]
    return json.loads(recorded[-1]["detail"]) if recorded else None


def recovery_chain(envelope: dict[str, Any], snapshot: dict[str, Any]) -> set[int]:
    """The generations that legitimately owned the attempt: its lead claim and each recovery."""
    current = snapshot.get("owner_generation")
    chain = {item["generation"] for item in snapshot.get("recoveries", [])}
    claim = envelope.get("delivery_lead_claim")
    if isinstance(claim, dict):
        chain.add(claim.get("generation"))
    return {generation for generation in chain
            if isinstance(generation, int) and isinstance(current, int) and generation <= current}


def unbound_resolutions(envelope: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Operator-resolved actions whose resolution is not bound to them, this attempt, and the chain.

    The snapshot lists only this attempt's resolutions, so a resolution
    recorded against another attempt is simply absent here (parent AC5).
    """
    resolved = [item for item in snapshot.get("actions", []) if (item.get("reason") or "").startswith("operator_resolved_")]
    if not resolved:
        return []
    chain = recovery_chain(envelope, snapshot)
    resolutions = snapshot.get("resolutions", [])
    blockers = []
    for item in resolved:
        reason = item["reason"]
        matching = [row for row in resolutions if row["action_id"] == item["action_id"]]
        bound = (len(matching) == 1 and matching[0]["owner_generation"] in chain
                 and matching[0]["disposition"] == "resolved_" + reason[len("operator_resolved_"):]
                 and (matching[0]["disposition"] != "resolved_completed" or matching[0]["result"] == item["result"]))
        if not bound:
            blockers.append({"id": item["action_id"], "kind": "action", "status": item["status"],
                             "reason": RESOLUTION_UNBOUND, "evidence_needed": EVIDENCE_NEEDED[RESOLUTION_UNBOUND]})
    return blockers


def recovery_eligibility(envelope: dict[str, Any], snapshot: dict[str, Any], *, lead_active: bool) -> dict[str, Any]:
    """Decide on a read-only snapshot whether and how an attempt may be recovered."""
    result: dict[str, Any] = {"recoverable": False, "reason": None, "mode": None, "action_id": None,
                              "checkpoint": None, "blockers": []}

    def refuse(reason: str, blockers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {**result, "reason": reason, "blockers": blockers or []}

    protocol = snapshot.get("execution_protocol_version")
    if protocol == 6:
        return refuse(V6_INSPECTION_ONLY)
    if protocol == 7:
        return refuse(V7_NOT_RECOVERABLE)
    if protocol != 8:
        return refuse(UNSUPPORTED_PROTOCOL)
    if snapshot.get("attempt_id") != envelope.get("attempt_id"):
        return refuse(ENVELOPE_CHANGED)
    if snapshot.get("status") != "started":
        return refuse(ATTEMPT_TERMINAL)
    if not lead_active:
        return refuse(LEAD_GENERATION_INACTIVE, [{"id": envelope["attempt_id"], "kind": "attempt",
                                                  "status": snapshot["status"], "reason": LEAD_GENERATION_INACTIVE,
                                                  "evidence_needed": EVIDENCE_NEEDED[LEAD_GENERATION_INACTIVE]}])
    observed = {item["action_id"] for item in snapshot.get("response_observations", [])}
    job = envelope.get("job_contract") or {}
    reconcilable = set(job.get("producer_instance_ids", [])) | set(job.get("verifier_instance_ids", []))

    def action_route(item: dict[str, Any]) -> str:
        eligible = item["action_id"] in observed and (item.get("request") or {}).get("instance_id") in reconcilable
        return EVIDENCE_NEEDED["observed_action" if eligible else "abandon_only"]

    uncertain = [{"id": item["action_id"], "kind": "action", "status": item["status"],
                  "reason": RECONCILIATION_REQUIRED, "evidence_needed": action_route(item)}
                 for item in snapshot.get("actions", []) if item["status"] in {"started", "unknown"}]
    uncertain += [{"id": item["call_id"], "kind": "manager_call", "status": item["status"],
                   "reason": RECONCILIATION_REQUIRED, "evidence_needed": EVIDENCE_NEEDED["abandon_only"]}
                  for item in snapshot.get("manager_calls", []) if item["status"] in {"started", "unknown"}]
    if uncertain:
        return refuse(RECONCILIATION_REQUIRED, uncertain)
    unbound = unbound_resolutions(envelope, snapshot)
    if unbound:
        return refuse(RESOLUTION_UNBOUND, unbound)
    if runtime_outcome(snapshot) is not None:
        return {**result, "recoverable": True, "mode": "seal"}
    actions = snapshot.get("actions", [])
    if not actions:
        return refuse(NO_RESTORABLE_CHECKPOINT, [{"id": envelope["attempt_id"], "kind": "attempt", "status": "started",
                                                  "reason": NO_RESTORABLE_CHECKPOINT,
                                                  "evidence_needed": EVIDENCE_NEEDED[NO_RESTORABLE_CHECKPOINT]}])
    latest = max(actions, key=lambda item: item["request"]["sequence"])
    link = next((item for item in snapshot.get("magentic_checkpoints", [])
                 if item["pending_kind"] == "worker" and item["pending_id"] == latest["action_id"]), None)

    def position_blocker(reason: str) -> list[dict[str, Any]]:
        return [{"id": latest["action_id"], "kind": "action", "status": latest["status"], "reason": reason,
                 "evidence_needed": EVIDENCE_NEEDED[reason]}]

    if link is None:
        return refuse(NO_RESTORABLE_CHECKPOINT, position_blocker(NO_RESTORABLE_CHECKPOINT))
    unsent = not _dispatched(snapshot, latest["action_id"])
    if latest["status"] == "completed":
        mode = "answer"
    elif unsent and (latest["status"] == "allowed"
                     or latest["status"] == "not_dispatched" and latest["reason"] == "recovery_unconsumed_grant"):
        mode = "pending"
    else:
        return refuse(CHECKPOINT_POSITION_UNRECOVERABLE, position_blocker(CHECKPOINT_POSITION_UNRECOVERABLE))
    return {**result, "recoverable": True, "mode": mode, "action_id": latest["action_id"], "checkpoint": link}


def rebuild_chartered_evidence_plan(envelope: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Decide which producer evidence recovery reuses and which it must capture once.

    Once a verifier input is bound, its diff and test digests are the evidence
    of record: recovery never reruns the targeted test. Before any input
    exists, the test is captured exactly once.
    """
    job = envelope["job_contract"]
    producer_completed = any(item["status"] == "completed" and item["request"]["instance_id"] in job["producer_instance_ids"]
                             for item in snapshot.get("actions", []))
    inputs = snapshot.get("verifier_inputs", [])
    if not producer_completed:
        if inputs:
            raise RecoveryRefused(EVIDENCE_BINDING_CONFLICT, "verifier input exists without a completed producer")
        return {"producer_completed": False, "diff_digest": None, "test_digest": None}
    if not inputs:
        return {"producer_completed": True, "diff_digest": None, "test_digest": None}
    diffs = {item["diff_digest"] for item in inputs}
    tests = {item["test_digest"] for item in inputs}
    if len(diffs) != 1 or len(tests) != 1:
        raise RecoveryRefused(EVIDENCE_BINDING_CONFLICT, "verifier inputs bind different evidence")
    return {"producer_completed": True, "diff_digest": diffs.pop(), "test_digest": tests.pop()}


def restore_position(envelope: dict[str, Any], snapshot: dict[str, Any], ledger_seq: int) -> dict[str, int]:
    """Count the manager calls and replans committed before a bound checkpoint."""
    manager_calls = snapshot.get("manager_calls", [])
    committed = {item["call_id"] for item in manager_calls if item["status"] == "completed"}
    before_pause = {item["action_id"] for item in snapshot.get("events", [])
                    if item["event"] == "manager_response_observed" and item["seq"] <= ledger_seq}
    replan_events = {item["action_id"] for item in snapshot.get("events", [])
                     if item["event"] == "replan_allowed" and item["seq"] <= ledger_seq}
    approved = [item for item in snapshot.get("replans", [])
                if item["status"] == "allowed" and item["replan_id"] in replan_events]
    if (len(approved) > envelope["limits"]["max_replans"]
            or sorted(item["sequence"] for item in approved) != list(range(1, len(approved) + 1))):
        raise ContractError("Magentic checkpoint replan lineage is inconsistent")
    return {"manager_calls_committed": len(committed & before_pause), "replans_committed": len(approved)}


def build_recovery_block(snapshot: dict[str, Any], *, replaced_draft_sha256: str | None) -> dict[str, Any]:
    """Project the ledger's interruption and recovery records into a receipt block."""
    resolved = {item["action_id"] for item in snapshot.get("actions", [])
                if str(item.get("reason")).startswith("operator_resolved_")}
    return {"schema_version": 1,
            "interruptions": [{key: item[key] for key in ("interruption_id", "cause", "owner_generation", "recorded_at")}
                              for item in snapshot.get("interruptions", [])],
            "recoveries": [{key: item[key] for key in ("recovery_id", "expected_generation", "generation",
                                                       "lead_generation", "actor", "mode", "released_action_ids",
                                                       "claimed_at")}
                           for item in snapshot.get("recoveries", [])],
            "resolutions": [item["resolution_id"] for item in snapshot.get("resolutions", [])
                            if item["action_id"] in resolved],
            "replaced_draft_sha256": replaced_draft_sha256}
