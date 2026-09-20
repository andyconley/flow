"""Flow-owned execution records. This module has no MAF dependency."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EXECUTION_PROTOCOL_VERSION = 2
MIXED_PROTOCOL_VERSION = 3
CLAUDE_PROTOCOL_VERSION = 4
MAGENTIC_PROTOCOL_VERSION = 5
MAX_TASK_BYTES = 4096
MAX_MESSAGE_BYTES = 65536
ALLOWED_PROVIDERS = frozenset({"ollama", "local-stub"})
MIXED_ASSIGNMENTS = (("test-engineer", "ollama"), ("lead-developer", "codex"))
CLAUDE_ASSIGNMENTS = (("test-engineer", "ollama"), ("quality-reviewer", "claude"))


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


def require_fields(record: dict[str, Any], fields: tuple[str, ...], *, kind: str,
                   max_bytes: int = MAX_MESSAGE_BYTES) -> None:
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"unsupported {kind} schema version")
    for field in fields:
        if field not in record or record[field] is None:
            raise ContractError(f"{kind} missing {field}")
    if len(canonical(record).encode("utf-8")) > max_bytes:
        raise ContractError(f"{kind} exceeds size limit")


def validate_envelope(envelope: dict[str, Any]) -> None:
    protocol_version = envelope.get("execution_protocol_version", 1)
    if protocol_version not in {1, EXECUTION_PROTOCOL_VERSION, MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION, MAGENTIC_PROTOCOL_VERSION}:
        raise ContractError("execution protocol version is unsupported")
    if protocol_version == MAGENTIC_PROTOCOL_VERSION:
        _validate_magentic_envelope(envelope)
        return
    shared = ("work_id", "attempt_id", "charter_digest", "charter_sources", "run_protocol_revision", "manifest_digest", "limits", "checkpoint_dir")
    legacy = ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model", "task_digest", "task")
    paired = protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}
    require_fields(envelope, shared + (("assignments",) if paired else legacy)
                   + (("source_commit", "source_files") if protocol_version == CLAUDE_PROTOCOL_VERSION else ()), kind="envelope")
    if paired:
        assignments = envelope["assignments"]
        if not isinstance(assignments, list) or len(assignments) != 2:
            raise ContractError("mixed job requires exactly two assignments")
        seen_instances: set[str] = set()
        seen_definitions: set[str] = set()
        seen_tasks: set[str] = set()
        for sequence, assignment in enumerate(assignments, 1):
            if not isinstance(assignment, dict) or set(assignment) != {"sequence", "assignment_id", "definition_digest", "instance_id", "role", "provider", "model", "task_digest", "task", "instructions"}:
                raise ContractError("mixed assignment fields are invalid")
            expected_pair = CLAUDE_ASSIGNMENTS if protocol_version == CLAUDE_PROTOCOL_VERSION else MIXED_ASSIGNMENTS
            if assignment["sequence"] != sequence or (assignment["role"], assignment["provider"]) != expected_pair[sequence - 1]:
                raise ContractError("mixed assignment order, role, or provider is invalid")
            for field in ("assignment_id", "instance_id", "model", "instructions"):
                if not isinstance(assignment[field], str) or not assignment[field].strip():
                    raise ContractError(f"mixed assignment {field} is invalid")
            if assignment["instance_id"] in seen_instances:
                raise ContractError("mixed assignment instance is duplicated")
            seen_instances.add(assignment["instance_id"])
            if assignment["definition_digest"] in seen_definitions:
                raise ContractError("mixed assignment definition is duplicated")
            seen_definitions.add(assignment["definition_digest"])
            if not isinstance(assignment["task"], str) or not assignment["task"].strip() or len(assignment["task"].encode()) > MAX_TASK_BYTES:
                raise ContractError("task is empty or exceeds size limit")
            if hashlib.sha256(assignment["task"].encode()).hexdigest() != assignment["task_digest"]:
                raise ContractError("task digest mismatch")
            if assignment["task_digest"] in seen_tasks:
                raise ContractError("mixed assignment task is duplicated")
            seen_tasks.add(assignment["task_digest"])
            if assignment["definition_digest"] != digest({"role": assignment["role"], "instructions": assignment["instructions"]}):
                raise ContractError("definition digest mismatch")
    elif envelope["role"] != "test-engineer" or envelope["provider"] not in ALLOWED_PROVIDERS:
        raise ContractError("role or provider is not allowed")
    sources = envelope["charter_sources"]
    if envelope["run_protocol_revision"] != 2 or not isinstance(sources, dict) or set(sources) != {"requirements", "acceptance"}:
        raise ContractError("charter source snapshot is invalid")
    for source in sources.values():
        if not isinstance(source, dict) or set(source) != {"path", "sha256"} or not isinstance(source["path"], str) or not source["path"].startswith(".flow/runs/") or any(part in {"", ".", ".."} for part in source["path"].split("/")) or not isinstance(source["sha256"], str) or len(source["sha256"]) != 64 or any(char not in "0123456789abcdef" for char in source["sha256"]):
            raise ContractError("charter source snapshot is invalid")
    if digest({"requirements": sources["requirements"]["sha256"], "acceptance": sources["acceptance"]["sha256"]}) != envelope["charter_digest"]:
        raise ContractError("charter source digest mismatch")
    if protocol_version == CLAUDE_PROTOCOL_VERSION:
        commit, files = envelope["source_commit"], envelope["source_files"]
        if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ContractError("Claude review source commit is invalid")
        expected_paths = ["cli/codex_worker.py", "tests/test_codex_worker.py"]
        if not isinstance(files, list) or [item.get("path") if isinstance(item, dict) else None for item in files] != expected_paths:
            raise ContractError("Claude review source paths are invalid")
        for item in files:
            value = item.get("sha256")
            if set(item) != {"path", "sha256"} or not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ContractError("Claude review source digest is invalid")
    if not paired:
        if not isinstance(envelope["task"], str) or not envelope["task"].strip() or len(envelope["task"].encode()) > MAX_TASK_BYTES:
            raise ContractError("task is empty or exceeds size limit")
        if hashlib.sha256(envelope["task"].encode()).hexdigest() != envelope["task_digest"]:
            raise ContractError("task digest mismatch")
    limits = envelope["limits"]
    expected_limits = ({"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "max_codex_calls": 1}
                       if protocol_version == MIXED_PROTOCOL_VERSION else
                       {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "max_claude_calls": 1}
                       if protocol_version == CLAUDE_PROTOCOL_VERSION else
                       {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "paid_budget_usd": 0})
    if not isinstance(limits, dict) or limits != expected_limits:
        raise ContractError("execution limits differ from the approved first slice")


def _hex_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate_magentic_envelope(envelope: dict[str, Any]) -> None:
    require_fields(envelope, ("work_id", "attempt_id", "charter_digest", "charter_sources",
                              "run_protocol_revision", "manifest_digest", "limits", "checkpoint_dir",
                              "source_commit", "worktree", "allowed_paths", "manager", "roster"), kind="envelope")
    sources = envelope["charter_sources"]
    if envelope["run_protocol_revision"] != 2 or not isinstance(sources, dict) or set(sources) != {"requirements", "acceptance"}:
        raise ContractError("charter source snapshot is invalid")
    for source in sources.values():
        if not isinstance(source, dict) or set(source) != {"path", "sha256"} or not isinstance(source["path"], str) or not source["path"].startswith(".flow/runs/") or any(part in {"", ".", ".."} for part in source["path"].split("/")) or not _hex_digest(source["sha256"]):
            raise ContractError("charter source snapshot is invalid")
    if digest({"requirements": sources["requirements"]["sha256"], "acceptance": sources["acceptance"]["sha256"]}) != envelope["charter_digest"]:
        raise ContractError("charter source digest mismatch")
    if not isinstance(envelope["manifest_digest"], str) or not _hex_digest(envelope["manifest_digest"]):
        raise ContractError("manifest digest is invalid")
    if not isinstance(envelope["source_commit"], str) or len(envelope["source_commit"]) != 40 or any(c not in "0123456789abcdef" for c in envelope["source_commit"]):
        raise ContractError("source commit is invalid")
    worktree = envelope["worktree"]
    if not isinstance(worktree, str) or not Path(worktree).is_absolute() or ".." in Path(worktree).parts:
        raise ContractError("worktree path is invalid")
    paths = envelope["allowed_paths"]
    if not isinstance(paths, list) or not paths or len(paths) != len(set(paths)):
        raise ContractError("allowed path scope is invalid")
    for path in paths:
        if not isinstance(path, str) or not path or Path(path).is_absolute() or any(part in {"", ".", ".."} for part in path.split("/")):
            raise ContractError("allowed path scope is invalid")
    manager = envelope["manager"]
    if not isinstance(manager, dict) or set(manager) != {"provider", "model"} or manager["provider"] not in {"ollama", "claude", "codex"} or not isinstance(manager["model"], str) or not manager["model"].strip():
        raise ContractError("manager binding is invalid")
    roster = envelope["roster"]
    if not isinstance(roster, list) or not roster or len(roster) > 6:
        raise ContractError("specialist roster is invalid")
    seen_ids: set[str] = set()
    for assignment in roster:
        if not isinstance(assignment, dict) or set(assignment) != {"assignment_id", "definition_digest", "instance_id", "role", "provider", "model", "instructions"}:
            raise ContractError("specialist binding is invalid")
        if assignment["provider"] not in {"ollama", "claude", "codex", "local-stub"}:
            raise ContractError("specialist provider is invalid")
        if any(not isinstance(assignment[k], str) or not assignment[k].strip() for k in ("assignment_id", "instance_id", "role", "model", "instructions")):
            raise ContractError("specialist identity is invalid")
        if assignment["assignment_id"] in seen_ids or assignment["instance_id"] in seen_ids:
            raise ContractError("specialist identity is duplicated")
        seen_ids.update((assignment["assignment_id"], assignment["instance_id"]))
        if assignment["definition_digest"] != digest({"role": assignment["role"], "instructions": assignment["instructions"]}):
            raise ContractError("specialist definition digest mismatch")
    limits = envelope["limits"]
    expected = {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2,
                "max_manager_calls": 12, "max_manager_rounds": 6, "max_paid_worker_calls": 1}
    if limits != expected:
        raise ContractError("Magentic limits differ from approved envelope")


def action_assignment(envelope: dict[str, Any], sequence: int) -> dict[str, Any]:
    """Select the immutable assignment bound to this logical action."""
    if execution_protocol_version(envelope) in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}:
        if type(sequence) is not int or not 1 <= sequence <= 2:
            raise ContractError("mixed action sequence is invalid")
        return envelope["assignments"][sequence - 1]
    if execution_protocol_version(envelope) == MAGENTIC_PROTOCOL_VERSION:
        raise ContractError("dynamic action requires an assignment identity")
    return envelope


def execution_protocol_version(envelope: dict[str, Any]) -> int:
    """Return the explicit protocol for a new attempt, defaulting old records to v1."""
    validate_envelope(envelope)
    return envelope.get("execution_protocol_version", 1)


def envelope_digest(envelope: dict[str, Any]) -> str:
    validate_envelope(envelope)
    return digest(envelope)


def expected_action_id(envelope: dict[str, Any], sequence: int) -> str:
    protocol_version = execution_protocol_version(envelope)
    if protocol_version == MAGENTIC_PROTOCOL_VERSION:
        raise ContractError("dynamic action identity requires its manager proposal")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ContractError("action sequence is invalid")
    if protocol_version == 1 and sequence != 1:
        raise ContractError("first slice permits one specialist request")
    if protocol_version == EXECUTION_PROTOCOL_VERSION and sequence > 3:
        raise ContractError("action sequence exceeds the approved slice")
    if protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION} and sequence > 2:
        raise ContractError("mixed action sequence exceeds the approved slice")
    assignment = action_assignment(envelope, sequence)
    identity = {
        "attempt_id": envelope["attempt_id"],
        "charter_digest": envelope["charter_digest"],
        "definition_digest": assignment["definition_digest"],
        "instance_id": assignment["instance_id"],
        "kind": "delegate", "sequence": sequence,
    }
    if protocol_version == EXECUTION_PROTOCOL_VERSION:
        identity["execution_protocol_version"] = protocol_version
    if protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}:
        identity["execution_protocol_version"] = protocol_version
        identity["assignment_id"] = assignment["assignment_id"]
    return digest(identity)


def validate_action(envelope: dict[str, Any], action: dict[str, Any]) -> None:
    require_fields(action, ("action_id", "attempt_id", "envelope_digest", "role", "instance_id", "provider", "model", "task_digest", "sequence", "kind"), kind="action")
    protocol_version = execution_protocol_version(envelope)
    if protocol_version == MAGENTIC_PROTOCOL_VERSION:
        _validate_magentic_action(envelope, action)
        return
    if action["kind"] != "delegate" or not isinstance(action["sequence"], int) or isinstance(action["sequence"], bool):
        raise ContractError("first slice permits one delegation")
    if protocol_version == 1 and action["sequence"] != 1:
        raise ContractError("first slice permits one delegation")
    if protocol_version == EXECUTION_PROTOCOL_VERSION and not 1 <= action["sequence"] <= 3:
        raise ContractError("action sequence exceeds the approved slice")
    if protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION} and not 1 <= action["sequence"] <= 2:
        raise ContractError("mixed action sequence exceeds the approved slice")
    assignment = action_assignment(envelope, action["sequence"])
    if protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}:
        for field in ("assignment_id", "definition_digest"):
            if action.get(field) != assignment[field]:
                raise ContractError(f"action {field} differs from approved assignment")
    for field in ("attempt_id", "role", "instance_id", "provider", "model", "task_digest"):
        expected = envelope[field] if field == "attempt_id" else assignment[field]
        if action[field] != expected:
            raise ContractError(f"action {field} differs from envelope")
    if action["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("action envelope digest mismatch")
    if action["action_id"] != expected_action_id(envelope, action["sequence"]):
        raise ContractError("action ID mismatch")


def expected_magentic_action_id(action: dict[str, Any]) -> str:
    fields = ("attempt_id", "envelope_digest", "assignment_id", "definition_digest", "instance_id",
              "sequence", "manager_turn", "task_digest", "parent_action_id", "checkpoint_id")
    return digest({"kind": "delegate", **{field: action[field] for field in fields}})


def _validate_magentic_action(envelope: dict[str, Any], action: dict[str, Any]) -> None:
    require_fields(action, ("assignment_id", "definition_digest", "manager_turn", "task", "rationale",
                            "checkpoint_id"), kind="Magentic action")
    if action["kind"] != "delegate" or type(action["sequence"]) is not int or not 1 <= action["sequence"] <= 6:
        raise ContractError("Magentic action sequence is invalid")
    if type(action["manager_turn"]) is not int or not 1 <= action["manager_turn"] <= 6:
        raise ContractError("Magentic manager turn is invalid")
    assignment = next((item for item in envelope["roster"] if item["assignment_id"] == action["assignment_id"]), None)
    if assignment is None:
        raise ContractError("Magentic selected an unlisted specialist")
    for field in ("definition_digest", "instance_id", "role", "provider", "model"):
        if action[field] != assignment[field]:
            raise ContractError(f"Magentic action {field} differs from roster")
    if action["attempt_id"] != envelope["attempt_id"] or action["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("Magentic action envelope link mismatch")
    if not isinstance(action["task"], str) or not action["task"].strip() or len(action["task"].encode()) > MAX_TASK_BYTES or hashlib.sha256(action["task"].encode()).hexdigest() != action["task_digest"]:
        raise ContractError("Magentic action task is invalid")
    if not isinstance(action["rationale"], str) or not action["rationale"].strip() or len(action["rationale"].encode()) > MAX_TASK_BYTES:
        raise ContractError("Magentic action rationale is invalid")
    if action.get("parent_action_id") is not None and not _hex_digest(action["parent_action_id"]):
        raise ContractError("Magentic parent action identity is invalid")
    if not isinstance(action["checkpoint_id"], str) or not action["checkpoint_id"].strip():
        raise ContractError("Magentic pending checkpoint is invalid")
    if action["action_id"] != expected_magentic_action_id(action):
        raise ContractError("Magentic action identity mismatch")


MAGENTIC_PHASES = frozenset({"facts", "plan", "progress", "replan", "replan_facts", "replan_plan", "final"})


def expected_manager_call_id(request: dict[str, Any]) -> str:
    fields = ("attempt_id", "envelope_digest", "sequence", "phase", "manager_round", "prompt_digest")
    identity = {"kind": "manager_model", **{field: request[field] for field in fields}}
    if request["phase"] in {"replan_facts", "replan_plan"}:
        identity.update({field: request[field] for field in ("replan_sequence", "replan_id")})
    return digest(identity)


def validate_manager_call(envelope: dict[str, Any], request: dict[str, Any]) -> None:
    if execution_protocol_version(envelope) != MAGENTIC_PROTOCOL_VERSION:
        raise ContractError("manager calls require protocol v5")
    require_fields(request, ("call_id", "attempt_id", "envelope_digest", "sequence", "phase",
                             "manager_round", "prompt_digest"), kind="manager call")
    if type(request["sequence"]) is not int or not 1 <= request["sequence"] <= 13 or type(request["manager_round"]) is not int or not 1 <= request["manager_round"] <= 7:
        raise ContractError("manager call position is invalid")
    if request["phase"] not in MAGENTIC_PHASES or not _hex_digest(request["prompt_digest"]):
        raise ContractError("manager call phase or prompt digest is invalid")
    if request["phase"] in {"replan_facts", "replan_plan"}:
        if type(request.get("replan_sequence")) is not int or not 1 <= request["replan_sequence"] <= 3 or request.get("replan_id") != expected_replan_id(envelope, request["replan_sequence"]):
            raise ContractError("manager replan identity is invalid")
    elif "replan_sequence" in request or "replan_id" in request:
        raise ContractError("non-replan manager call carries replan authority")
    if request["attempt_id"] != envelope["attempt_id"] or request["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("manager call envelope link mismatch")
    if request["call_id"] != expected_manager_call_id(request):
        raise ContractError("manager call identity mismatch")


def expected_replan_id(envelope: dict[str, Any], sequence: int) -> str:
    protocol = execution_protocol_version(envelope)
    if protocol == MAGENTIC_PROTOCOL_VERSION:
        if type(sequence) is not int or not 1 <= sequence <= 3:
            raise ContractError("replan sequence exceeds the approved slice")
        return digest({"attempt_id": envelope["attempt_id"], "envelope_digest": envelope_digest(envelope),
                       "execution_protocol_version": 5, "kind": "replan", "sequence": sequence})
    if protocol != EXECUTION_PROTOCOL_VERSION:
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
    if execution_protocol_version(envelope) == MAGENTIC_PROTOCOL_VERSION:
        require_fields(replan, ("replan_id", "attempt_id", "envelope_digest", "sequence", "kind", "proposal"), kind="replan")
        if replan["kind"] != "replan" or type(replan["sequence"]) is not int or not 1 <= replan["sequence"] <= 3 or not isinstance(replan["proposal"], dict) or not replan["proposal"]:
            raise ContractError("Magentic replan proposal is invalid")
        if replan["attempt_id"] != envelope["attempt_id"] or replan["envelope_digest"] != envelope_digest(envelope) or replan["replan_id"] != expected_replan_id(envelope, replan["sequence"]):
            raise ContractError("Magentic replan identity mismatch")
        return
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


def validate_result(envelope: dict[str, Any], result: dict[str, Any], *, action: dict[str, Any] | None = None) -> None:
    require_fields(result, ("status", "provider", "model", "physical_call", "evidence_level", "output", "output_sha256"), kind="result")
    if execution_protocol_version(envelope) == MAGENTIC_PROTOCOL_VERSION:
        if action is None:
            raise ContractError("Magentic result requires selected action identity")
        validate_action(envelope, action)
        assignment = next(item for item in envelope["roster"] if item["assignment_id"] == action["assignment_id"])
    elif execution_protocol_version(envelope) in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}:
        if action is None:
            raise ContractError("mixed result requires an action identity")
        validate_action(envelope, action)
        assignment = action_assignment(envelope, action["sequence"])
    else:
        assignment = envelope
    if result["status"] != "completed" or result["provider"] != assignment["provider"] or result["model"] != assignment["model"]:
        raise ContractError("result status, provider, or model differs from approved envelope")
    physical = assignment["provider"] in {"ollama", "codex", "claude"}
    if type(result["physical_call"]) is not bool or result["physical_call"] != physical:
        raise ContractError("result physical-call claim contradicts provider")
    expected_evidence = ({"ollama": "flow_observed_local_http_response", "codex": "flow_observed_codex_cli_completed_turn", "claude": "flow_observed_claude_cli_completed_turn", "local-stub": "local_stub"})[assignment["provider"]]
    if result["evidence_level"] != expected_evidence:
        raise ContractError("result evidence level contradicts provider")
    output = result["output"]
    if not isinstance(output, str) or not output or len(output.encode("utf-8")) > 4096:
        raise ContractError("result output is empty or too large")
    if hashlib.sha256(output.encode("utf-8")).hexdigest() != result["output_sha256"]:
        raise ContractError("result output digest mismatch")
    if assignment["provider"] == "claude" and (not isinstance(result.get("session_id"), str) or not result["session_id"]):
        raise ContractError("Claude result session identity is absent")
    usage = result.get("usage")
    if usage is not None:
        if not isinstance(usage, dict) or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in usage.values()):
            raise ContractError("result usage is invalid")


def validate_receipt(envelope: dict[str, Any], receipt: dict[str, Any]) -> None:
    protocol_version = execution_protocol_version(envelope)
    if protocol_version == MAGENTIC_PROTOCOL_VERSION:
        _validate_magentic_receipt(envelope, receipt)
        return
    common = ("work_id", "attempt_id", "envelope_digest", "charter_digest", "manifest_digest", "status", "actions")
    paired = protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}
    require_fields(receipt, common + (() if paired else ("definition_digest", "provider")), kind="receipt")
    for field in ("work_id", "attempt_id", "charter_digest", "manifest_digest") + (() if paired else ("definition_digest", "provider")):
        if receipt[field] != envelope[field]:
            raise ContractError(f"receipt {field} link mismatch")
    if receipt["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("receipt envelope link mismatch")
    if receipt.get("charter_sources") != envelope["charter_sources"] or receipt.get("run_protocol_revision") != envelope["run_protocol_revision"]:
        raise ContractError("receipt charter source link mismatch")
    if receipt["status"] not in {"completed", "failed", "denied", "unknown"} or not isinstance(receipt["actions"], list):
        raise ContractError("receipt status or actions invalid")
    if protocol_version == 1:
        return
    require_fields(receipt, ("execution_protocol_version", "replans", "checkpoints"), kind="versioned receipt")
    if receipt["execution_protocol_version"] != protocol_version:
        raise ContractError("receipt execution protocol link mismatch")
    if paired:
        if receipt.get("assignments") != envelope["assignments"]:
            raise ContractError("receipt mixed assignments link mismatch")
        if receipt["replans"] != []:
            raise ContractError("mixed receipt cannot claim replans")
        seen_sequences: set[int] = set()
        for item in receipt["actions"]:
            if not isinstance(item, dict) or not isinstance(item.get("request"), dict):
                raise ContractError("mixed receipt action is invalid")
            request = item["request"]
            validate_action(envelope, request)
            sequence = request["sequence"]
            if sequence in seen_sequences or item.get("action_id") != request["action_id"]:
                raise ContractError("mixed receipt action identity is duplicated or changed")
            seen_sequences.add(sequence)
            if item.get("status") not in {"allowed", "started", "completed", "failed", "denied", "unknown", "not_dispatched"}:
                raise ContractError("mixed receipt action status is invalid")
            if item["status"] == "completed":
                if not isinstance(item.get("result"), dict):
                    raise ContractError("completed mixed action lacks a result")
                validate_result(envelope, item["result"], action=request)
            elif item.get("result") is not None and item["status"] != "failed":
                raise ContractError("mixed action result contradicts status")
        if receipt["status"] == "completed":
            if [item["request"]["sequence"] for item in receipt["actions"]] != [1, 2] or any(item["status"] != "completed" for item in receipt["actions"]):
                raise ContractError("completed mixed receipt requires both completed actions")
            if protocol_version == MIXED_PROTOCOL_VERSION:
                fixture_diff = receipt.get("fixture_diff")
                if not isinstance(fixture_diff, dict) or set(fixture_diff) != {"changed_files", "before_sha256", "after_sha256", "diff_sha256", "behavior_check"}:
                    raise ContractError("completed mixed receipt requires a fixture diff")
                if fixture_diff["changed_files"] != ["greet.py"] or fixture_diff["behavior_check"] != "passed":
                    raise ContractError("mixed fixture scope or behavior check is invalid")
                for key in ("before_sha256", "after_sha256", "diff_sha256"):
                    value = fixture_diff[key]
                    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                        raise ContractError("mixed fixture digest is invalid")
                if fixture_diff["before_sha256"] == fixture_diff["after_sha256"]:
                    raise ContractError("mixed fixture has no changed content")
            else:
                if receipt.get("source_commit") != envelope["source_commit"] or receipt.get("source_files") != envelope["source_files"]:
                    raise ContractError("Claude review source link mismatch")
                review = receipt.get("review_artifact")
                if not isinstance(review, dict) or set(review) != {"path", "sha256", "plan_sha256"} or review["path"] != "review-output.md":
                    raise ContractError("Claude review artifact link is invalid")
                for key in ("sha256", "plan_sha256"):
                    value = review[key]
                    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                        raise ContractError("Claude review artifact digest is invalid")
                if review["plan_sha256"] != receipt["actions"][0]["result"]["output_sha256"]:
                    raise ContractError("Claude review plan link mismatch")
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


def _validate_magentic_receipt(envelope: dict[str, Any], receipt: dict[str, Any]) -> None:
    require_fields(receipt, ("work_id", "attempt_id", "envelope_digest", "charter_digest", "manifest_digest",
                             "status", "execution_protocol_version", "roster", "manager_calls", "actions",
                             "replans", "checkpoints", "evidence"), kind="Magentic receipt", max_bytes=512 * 1024)
    if receipt["execution_protocol_version"] != 5 or receipt["status"] not in {"completed", "failed", "denied", "unknown"}:
        raise ContractError("Magentic receipt status or protocol is invalid")
    for field in ("work_id", "attempt_id", "charter_digest", "manifest_digest"):
        if receipt[field] != envelope[field]:
            raise ContractError(f"Magentic receipt {field} link mismatch")
    if receipt["envelope_digest"] != envelope_digest(envelope) or receipt.get("charter_sources") != envelope["charter_sources"] or receipt.get("run_protocol_revision") != envelope["run_protocol_revision"] or receipt["roster"] != envelope["roster"]:
        raise ContractError("Magentic receipt envelope or roster link mismatch")
    evidence = receipt["evidence"]
    if not isinstance(evidence, dict) or any(evidence.get(field) != envelope[field] for field in ("source_commit", "worktree", "allowed_paths")):
        raise ContractError("Magentic receipt source or scope link mismatch")
    for key in ("tree_sha256", "diff_sha256"):
        if key in evidence and not _hex_digest(evidence[key]):
            raise ContractError("Magentic receipt evidence digest is invalid")
    for key in ("manager_calls", "actions", "replans", "checkpoints"):
        if not isinstance(receipt[key], list):
            raise ContractError("Magentic receipt decision list is invalid")
    seen_calls: set[str] = set()
    for item in receipt["manager_calls"]:
        if not isinstance(item, dict) or not isinstance(item.get("request"), dict):
            raise ContractError("Magentic manager receipt is invalid")
        request = item["request"]
        validate_manager_call(envelope, request)
        if item.get("call_id") != request["call_id"] or request["call_id"] in seen_calls or item.get("status") not in {"allowed", "started", "completed", "denied", "unknown"}:
            raise ContractError("Magentic manager receipt identity or status is invalid")
        seen_calls.add(request["call_id"])
        if item["status"] == "completed" and not isinstance(item.get("result"), dict):
            raise ContractError("Magentic completed manager call lacks observed result")
    seen_actions: set[str] = set()
    for item in receipt["actions"]:
        if not isinstance(item, dict) or not isinstance(item.get("request"), dict):
            raise ContractError("Magentic action receipt is invalid")
        action = item["request"]
        validate_action(envelope, action)
        if item.get("action_id") != action["action_id"] or action["action_id"] in seen_actions or item.get("status") not in {"allowed", "started", "completed", "failed", "denied", "unknown", "not_dispatched"}:
            raise ContractError("Magentic action receipt identity or status is invalid")
        seen_actions.add(action["action_id"])
        if item["status"] == "completed":
            validate_result(envelope, item.get("result"), action=action)
    if receipt["status"] == "completed":
        completed = [item["request"] for item in receipt["actions"] if item["status"] == "completed"]
        producers = [item for item in completed if item["role"] == "lead-developer" and item["provider"] == "claude"]
        if len(producers) != 1 or not any(item["role"] == "test-engineer" and item["instance_id"] != producers[0]["instance_id"] and item["sequence"] > producers[0]["sequence"] for item in completed):
            raise ContractError("completed Magentic receipt requires Claude producer and later distinct verifier")
        baseline, edit, tests = (evidence.get(key) for key in ("baseline", "edit", "tests"))
        if not isinstance(baseline, dict) or baseline.get("source_commit") != envelope["source_commit"] or not _hex_digest(baseline.get("regression_diff_sha256")) or not isinstance(baseline.get("files"), dict) or not all(_hex_digest(v) for v in baseline["files"].values()):
            raise ContractError("Magentic baseline evidence is invalid")
        if not isinstance(edit, dict) or not isinstance(edit.get("changed_files"), list) or not edit["changed_files"] or not set(edit["changed_files"]).issubset(set(envelope["allowed_paths"])) or "cli/codex_worker.py" not in edit["changed_files"] or not _hex_digest(edit.get("diff_sha256")) or not isinstance(edit.get("diff_path"), str) or not edit["diff_path"] or not isinstance(edit.get("files"), dict) or not all(_hex_digest(v) for v in edit["files"].values()):
            raise ContractError("Magentic edit evidence is invalid")
        if not isinstance(tests, dict) or tests.get("status") != "passed" or not isinstance(tests.get("command"), list) or not tests["command"] or not all(isinstance(v, str) and v for v in tests["command"]) or not _hex_digest(tests.get("output_sha256")):
            raise ContractError("Magentic focused test evidence is invalid")


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
