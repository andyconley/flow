"""Flow-owned execution records. This module has no MAF dependency."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EXECUTION_PROTOCOL_VERSION = 2
MAX_TASK_BYTES = 4096
MAX_MESSAGE_BYTES = 65536
ALLOWED_PROVIDERS = frozenset({"ollama", "local-stub"})


class ContractError(ValueError):
    """An execution record violates Flow's versioned contract."""


def canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"record is not canonical JSON: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_fields(record: dict[str, Any], fields: tuple[str, ...], *, kind: str) -> None:
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"unsupported {kind} schema version")
    for field in fields:
        if field not in record or record[field] is None:
            raise ContractError(f"{kind} missing {field}")
    if len(canonical(record).encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ContractError(f"{kind} exceeds size limit")


def validate_envelope(envelope: dict[str, Any]) -> None:
    require_fields(envelope, (
        "work_id", "attempt_id", "charter_digest", "charter_sources", "run_protocol_revision", "manifest_digest", "assignment_id",
        "definition_digest", "instance_id", "role", "provider", "model", "task_digest",
        "task", "limits", "checkpoint_dir",
    ), kind="envelope")
    if envelope["role"] != "test-engineer" or envelope["provider"] not in ALLOWED_PROVIDERS:
        raise ContractError("role or provider is not allowed")
    sources = envelope["charter_sources"]
    if envelope["run_protocol_revision"] != 2 or not isinstance(sources, dict) or set(sources) != {"requirements", "acceptance"}:
        raise ContractError("charter source snapshot is invalid")
    for source in sources.values():
        if not isinstance(source, dict) or set(source) != {"path", "sha256"} or not isinstance(source["path"], str) or not source["path"].startswith(".flow/runs/") or any(part in {"", ".", ".."} for part in source["path"].split("/")) or not isinstance(source["sha256"], str) or len(source["sha256"]) != 64 or any(char not in "0123456789abcdef" for char in source["sha256"]):
            raise ContractError("charter source snapshot is invalid")
    if digest({"requirements": sources["requirements"]["sha256"], "acceptance": sources["acceptance"]["sha256"]}) != envelope["charter_digest"]:
        raise ContractError("charter source digest mismatch")
    if not isinstance(envelope["task"], str) or not envelope["task"].strip() or len(envelope["task"].encode()) > MAX_TASK_BYTES:
        raise ContractError("task is empty or exceeds size limit")
    if hashlib.sha256(envelope["task"].encode()).hexdigest() != envelope["task_digest"]:
        raise ContractError("task digest mismatch")
    limits = envelope["limits"]
    if not isinstance(limits, dict) or limits != {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "paid_budget_usd": 0}:
        raise ContractError("execution limits differ from the approved first slice")
    protocol_version = envelope.get("execution_protocol_version", 1)
    if protocol_version not in {1, EXECUTION_PROTOCOL_VERSION}:
        raise ContractError("execution protocol version is unsupported")


def execution_protocol_version(envelope: dict[str, Any]) -> int:
    """Return the explicit protocol for a new attempt, defaulting old records to v1."""
    validate_envelope(envelope)
    return envelope.get("execution_protocol_version", 1)


def envelope_digest(envelope: dict[str, Any]) -> str:
    validate_envelope(envelope)
    return digest(envelope)


def expected_action_id(envelope: dict[str, Any], sequence: int) -> str:
    protocol_version = execution_protocol_version(envelope)
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ContractError("action sequence is invalid")
    if protocol_version == 1 and sequence != 1:
        raise ContractError("first slice permits one specialist request")
    if protocol_version == EXECUTION_PROTOCOL_VERSION and sequence > 3:
        raise ContractError("action sequence exceeds the approved slice")
    identity = {
        "attempt_id": envelope["attempt_id"],
        "charter_digest": envelope["charter_digest"],
        "definition_digest": envelope["definition_digest"],
        "instance_id": envelope["instance_id"],
        "kind": "delegate", "sequence": sequence,
    }
    if protocol_version == EXECUTION_PROTOCOL_VERSION:
        identity["execution_protocol_version"] = protocol_version
    return digest(identity)


def validate_action(envelope: dict[str, Any], action: dict[str, Any]) -> None:
    require_fields(action, ("action_id", "attempt_id", "envelope_digest", "role", "instance_id", "provider", "model", "task_digest", "sequence", "kind"), kind="action")
    protocol_version = execution_protocol_version(envelope)
    if action["kind"] != "delegate" or not isinstance(action["sequence"], int) or isinstance(action["sequence"], bool):
        raise ContractError("first slice permits one delegation")
    if protocol_version == 1 and action["sequence"] != 1:
        raise ContractError("first slice permits one delegation")
    if protocol_version == EXECUTION_PROTOCOL_VERSION and not 1 <= action["sequence"] <= 3:
        raise ContractError("action sequence exceeds the approved slice")
    for field in ("attempt_id", "role", "instance_id", "provider", "model", "task_digest"):
        if action[field] != envelope[field]:
            raise ContractError(f"action {field} differs from envelope")
    if action["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("action envelope digest mismatch")
    if action["action_id"] != expected_action_id(envelope, action["sequence"]):
        raise ContractError("action ID mismatch")


def expected_replan_id(envelope: dict[str, Any], sequence: int) -> str:
    if execution_protocol_version(envelope) != EXECUTION_PROTOCOL_VERSION:
        raise ContractError("replans require execution protocol v2")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or not 1 <= sequence <= 3:
        raise ContractError("replan sequence exceeds the approved slice")
    return digest({
        "attempt_id": envelope["attempt_id"],
        "charter_digest": envelope["charter_digest"],
        "definition_digest": envelope["definition_digest"],
        "instance_id": envelope["instance_id"],
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
        "kind": "replan",
        "sequence": sequence,
    })


def validate_replan(envelope: dict[str, Any], replan: dict[str, Any]) -> None:
    """Validate a Flow-owned replan request without giving it action authority."""
    require_fields(replan, ("replan_id", "attempt_id", "envelope_digest", "role", "instance_id", "provider", "model", "task_digest", "sequence", "kind", "proposal"), kind="replan")
    if execution_protocol_version(envelope) != EXECUTION_PROTOCOL_VERSION:
        raise ContractError("replans require execution protocol v2")
    if replan["kind"] != "replan" or not isinstance(replan["sequence"], int) or isinstance(replan["sequence"], bool) or not 1 <= replan["sequence"] <= 3:
        raise ContractError("replan sequence exceeds the approved slice")
    if not isinstance(replan["proposal"], dict) or not replan["proposal"]:
        raise ContractError("replan proposal is invalid")
    for field in ("attempt_id", "role", "instance_id", "provider", "model", "task_digest"):
        if replan[field] != envelope[field]:
            raise ContractError(f"replan {field} differs from envelope")
    if replan["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("replan envelope digest mismatch")
    if replan["replan_id"] != expected_replan_id(envelope, replan["sequence"]):
        raise ContractError("replan ID mismatch")


def validate_result(envelope: dict[str, Any], result: dict[str, Any]) -> None:
    require_fields(result, ("status", "provider", "model", "physical_call", "evidence_level", "output", "output_sha256"), kind="result")
    if result["status"] != "completed" or result["provider"] != envelope["provider"] or result["model"] != envelope["model"]:
        raise ContractError("result status, provider, or model differs from approved envelope")
    physical = envelope["provider"] == "ollama"
    if type(result["physical_call"]) is not bool or result["physical_call"] != physical:
        raise ContractError("result physical-call claim contradicts provider")
    expected_evidence = "flow_observed_local_http_response" if physical else "local_stub"
    if result["evidence_level"] != expected_evidence:
        raise ContractError("result evidence level contradicts provider")
    output = result["output"]
    if not isinstance(output, str) or not output or len(output.encode("utf-8")) > 4096:
        raise ContractError("result output is empty or too large")
    if hashlib.sha256(output.encode("utf-8")).hexdigest() != result["output_sha256"]:
        raise ContractError("result output digest mismatch")
    usage = result.get("usage")
    if usage is not None:
        if not isinstance(usage, dict) or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in usage.values()):
            raise ContractError("result usage is invalid")


def validate_receipt(envelope: dict[str, Any], receipt: dict[str, Any]) -> None:
    require_fields(receipt, ("work_id", "attempt_id", "envelope_digest", "charter_digest", "manifest_digest", "definition_digest", "provider", "status", "actions"), kind="receipt")
    for field in ("work_id", "attempt_id", "charter_digest", "manifest_digest", "definition_digest", "provider"):
        if receipt[field] != envelope[field]:
            raise ContractError(f"receipt {field} link mismatch")
    if receipt["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("receipt envelope link mismatch")
    if receipt.get("charter_sources") != envelope["charter_sources"] or receipt.get("run_protocol_revision") != envelope["run_protocol_revision"]:
        raise ContractError("receipt charter source link mismatch")
    if receipt["status"] not in {"completed", "failed", "denied", "unknown"} or not isinstance(receipt["actions"], list):
        raise ContractError("receipt status or actions invalid")
    if execution_protocol_version(envelope) == 1:
        return
    require_fields(receipt, ("execution_protocol_version", "replans", "checkpoints"), kind="v2 receipt")
    if receipt["execution_protocol_version"] != EXECUTION_PROTOCOL_VERSION:
        raise ContractError("receipt execution protocol link mismatch")
    if not isinstance(receipt["replans"], list) or not isinstance(receipt["checkpoints"], list):
        raise ContractError("receipt v2 decision or checkpoint list is invalid")
    seen_replans: set[tuple[str, int]] = set()
    for replan in receipt["replans"]:
        if not isinstance(replan, dict) or not isinstance(replan.get("replan_id"), str) or not isinstance(replan.get("sequence"), int) or replan.get("status") not in {"allowed", "denied"} or not isinstance(replan.get("reason"), str):
            raise ContractError("receipt replan is invalid")
        key = (replan["replan_id"], replan["sequence"])
        if key in seen_replans:
            raise ContractError("receipt replan is duplicated")
        seen_replans.add(key)
    seen_positions: set[tuple[str, int]] = set()
    for checkpoint in receipt["checkpoints"]:
        if not isinstance(checkpoint, dict) or checkpoint.get("kind") not in {"delegate", "pending_delegate", "replan"} or not isinstance(checkpoint.get("sequence"), int) or not isinstance(checkpoint.get("file_sha256"), str) or len(checkpoint["file_sha256"]) != 64:
            raise ContractError("receipt checkpoint is invalid")
        position = (checkpoint["kind"], checkpoint["sequence"])
        if position in seen_positions:
            raise ContractError("receipt checkpoint position is duplicated")
        seen_positions.add(position)
    endpoint_evidence = receipt.get("endpoint_evidence")
    if endpoint_evidence is None:
        return
    if not isinstance(endpoint_evidence, dict) or endpoint_evidence.get("status") not in {"observed", "unavailable"} or not isinstance(endpoint_evidence.get("actions"), list):
        raise ContractError("receipt endpoint evidence is invalid")
    status = endpoint_evidence["status"]
    path, sha256 = endpoint_evidence.get("path"), endpoint_evidence.get("sha256")
    if (path is None) != (sha256 is None) or (path is not None and (not isinstance(path, str) or not path or not isinstance(sha256, str) or len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256))):
        raise ContractError("receipt endpoint evidence link is invalid")
    if status == "observed" and path is None:
        raise ContractError("observed endpoint evidence requires a sealed link")
    seen_actions: set[str] = set()
    for action in endpoint_evidence["actions"]:
        if not isinstance(action, dict) or not isinstance(action.get("action_id"), str) or not action["action_id"] or type(action.get("flow_send_observed")) is not bool:
            raise ContractError("receipt endpoint action evidence is invalid")
        arrivals = action.get("endpoint_arrivals")
        if arrivals is not None and (not isinstance(arrivals, int) or isinstance(arrivals, bool) or arrivals < 0):
            raise ContractError("receipt endpoint arrival count is invalid")
        if status == "unavailable" and arrivals is not None:
            raise ContractError("unavailable endpoint evidence cannot claim arrivals")
        if action["action_id"] in seen_actions:
            raise ContractError("receipt endpoint action evidence is duplicated")
        seen_actions.add(action["action_id"])


RECOVERY_DISPOSITIONS = frozenset({"resolved_completed", "resolved_not_dispatched", "still_unknown"})


def validate_recovery_evidence(evidence: list[dict[str, Any]]) -> None:
    """Validate immutable evidence references used by an operator resolution.

    The ledger deliberately retains references and digests rather than mutable
    evidence bytes. Callers that accept filesystem paths must independently
    verify the path and its digest before recording this contract.
    """
    if not isinstance(evidence, list) or not evidence:
        raise ContractError("recovery resolution requires immutable evidence")
    seen: set[tuple[str, str]] = set()
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"kind", "path", "sha256"}:
            raise ContractError("recovery evidence is invalid")
        if not isinstance(item["kind"], str) or not item["kind"].strip() or not isinstance(item["path"], str) or not item["path"].strip():
            raise ContractError("recovery evidence is invalid")
        value = item["sha256"]
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ContractError("recovery evidence digest is invalid")
        key = (item["path"], value)
        if key in seen:
            raise ContractError("recovery evidence is duplicated")
        seen.add(key)


def validate_recovery_resolution(disposition: str, explanation: str, evidence: list[dict[str, Any]]) -> None:
    if disposition not in RECOVERY_DISPOSITIONS:
        raise ContractError("recovery disposition is invalid")
    if not isinstance(explanation, str) or not explanation.strip() or len(explanation.encode("utf-8")) > 4096:
        raise ContractError("recovery explanation is invalid")
    validate_recovery_evidence(evidence)
