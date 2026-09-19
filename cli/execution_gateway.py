"""Flow's application gateway for one supervised local MAF specialist call."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable

from execution_contracts import ContractError, canonical, digest, envelope_digest, validate_action, validate_receipt, validate_result
from execution_ledger import ExecutionLedger, utc_now
from fsutil import repo_root, write_atomic
from local_worker import call_local
from maf_supervisor import run_maf
from orchestration import validate_orchestration
from paths import SCAFFOLD_DIR
from runstate import status as run_status
from sync import agent_body, merge_user_overlay


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _run_file(root: Path, run_dir: Path, raw: str) -> Path:
    path = (root / raw).resolve()
    if not _inside(path, run_dir.resolve()) or not path.is_file():
        raise ContractError("task or approved source is outside the run or absent")
    return path


def _effective_specialist() -> str:
    _, manifest = merge_user_overlay(SCAFFOLD_DIR)
    matches = [entry for entry in manifest.get("agents", []) if entry.get("name") == "test-engineer"]
    if len(matches) != 1:
        raise ContractError("effective test-engineer definition is absent or ambiguous")
    entry = matches[0]
    return agent_body(entry, entry["_root"], SCAFFOLD_DIR, manifest.get("codex", {}).get("agent_defaults", {}))


def _write_snapshot(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def prepare(work_id: str, assignment_id: str, task_file: str, *, root: Path | None = None,
            test_provider: str | None = None) -> tuple[dict[str, Any], Path, ExecutionLedger]:
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    state = run_status(work_id, root=project_root)
    if state.get("state") != "implementing" or state.get("protocol_revision") != 2:
        raise ContractError("execution requires an implementing revision-2 run")
    valid, _, findings = validate_orchestration(work_id, "dispatch", root=project_root)
    if not valid:
        raise ContractError("orchestration dispatch invalid: " + "; ".join(f.message for f in findings))
    manifest_path = run_dir / "orchestration.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    matches = [a for a in manifest["assignments"] if a.get("id") == assignment_id]
    if len(matches) != 1 or matches[0].get("role") != "test-engineer":
        raise ContractError("approved test-engineer assignment not found")
    assignment = matches[0]
    execution = assignment.get("execution")
    if not isinstance(execution, dict) or execution.get("provider") != "ollama" or not isinstance(execution.get("model"), str) or not execution["model"].strip():
        raise ContractError("assignment lacks approved local Ollama execution settings")
    task_path = _run_file(project_root, run_dir, task_file)
    task = task_path.read_text()
    if not task.strip() or len(task.encode()) > 4096:
        raise ContractError("task is empty or too large")
    artifacts = state.get("artifacts", {})
    requirements = _run_file(project_root, run_dir, artifacts.get("requirements", ""))
    acceptance = _run_file(project_root, run_dir, artifacts.get("acceptance_criteria", ""))
    requirements_bytes, acceptance_bytes = requirements.read_bytes(), acceptance.read_bytes()
    instructions = _effective_specialist()
    attempt_id = uuid.uuid4().hex
    execution_dir = run_dir / "execution"
    execution_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(execution_dir, 0o700)
    attempt_dir = execution_dir / attempt_id
    attempt_dir.mkdir(mode=0o700)
    (attempt_dir / "checkpoints").mkdir(mode=0o700)
    # The orchestration manifest changes at handback; retain the exact bytes
    # authorized at dispatch so its digest remains independently checkable.
    for source_bytes, snapshot_name in ((manifest_bytes, "manifest.snapshot.json"),
                                        (requirements_bytes, "requirements.snapshot.md"),
                                        (acceptance_bytes, "acceptance.snapshot.md")):
        _write_snapshot(attempt_dir / snapshot_name, source_bytes)
    if (manifest_path.read_bytes() != manifest_bytes or requirements.read_bytes() != requirements_bytes
            or acceptance.read_bytes() != acceptance_bytes):
        raise ContractError("approved execution sources changed during preparation")
    if test_provider not in {None, "local-stub"}:
        raise ContractError("unsupported test provider")
    envelope = {"schema_version": 1, "work_id": work_id, "attempt_id": attempt_id,
                "charter_digest": digest({"requirements": hashlib.sha256(requirements_bytes).hexdigest(), "acceptance": hashlib.sha256(acceptance_bytes).hexdigest()}),
                "charter_sources": {"requirements": {"path": str(requirements.relative_to(project_root)), "sha256": hashlib.sha256(requirements_bytes).hexdigest()},
                                    "acceptance": {"path": str(acceptance.relative_to(project_root)), "sha256": hashlib.sha256(acceptance_bytes).hexdigest()}},
                "run_protocol_revision": state["protocol_revision"],
                "manifest_digest": hashlib.sha256(manifest_bytes).hexdigest(), "assignment_id": assignment_id,
                "definition_digest": hashlib.sha256(instructions.encode()).hexdigest(),
                "instance_id": "test-engineer-1", "role": "test-engineer", "provider": test_provider or "ollama", "model": execution["model"] if test_provider is None else "deterministic-stub",
                "task_digest": hashlib.sha256(task.encode()).hexdigest(), "task": task, "instructions": instructions,
                "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "paid_budget_usd": 0},
                "checkpoint_dir": str(attempt_dir / "checkpoints")}
    envelope_digest(envelope)
    write_atomic(attempt_dir / "envelope.json", canonical(envelope) + "\n", mode=0o600)
    ledger = ExecutionLedger(run_dir / "execution" / "ledger.sqlite")
    ledger.create_attempt(envelope)
    return envelope, attempt_dir, ledger


def execute_local(work_id: str, assignment_id: str, task_file: str, *, root: Path | None = None,
                  adapter: Callable[..., dict[str, Any]] | None = None,
                  supervisor: Callable[..., dict[str, Any]] | None = None,
                  python_path: str | None = None) -> dict[str, Any]:
    envelope, attempt_dir, ledger = prepare(work_id, assignment_id, task_file, root=root,
                                            test_provider="local-stub" if adapter is not None else None)
    if supervisor is None:
        supervisor = run_maf
    adapter = adapter or call_local
    aid = envelope["attempt_id"]
    outcome: dict[str, Any] = {}
    failure = ""
    validated_checkpoint_id: str | None = None

    def on_propose(action: dict[str, Any]) -> dict[str, Any]:
        validate_action(envelope, action)
        decision = ledger.decide(envelope, action)
        if not decision["allowed"]:
            return {"status": "denied", "reason": decision["reason"], "action_id": action["action_id"]}
        if not ledger.consume_grant(action["action_id"], decision["grant_id"]):
            current = next((item for item in ledger.snapshot(aid)["actions"] if item["action_id"] == action["action_id"]), None)
            reason = current["reason"] if current and current["reason"] == "grant_expired" else "grant_reused"
            return {"status": "denied", "reason": reason, "action_id": action["action_id"]}
        try:
            result = adapter(envelope)
            validate_result(envelope, result)
            ledger.complete(action["action_id"], result)
            return {"status": "completed", "action_id": action["action_id"], "output": result["output"]}
        except Exception as exc:
            ledger.mark_unknown(action["action_id"], "adapter_outcome_uncertain")
            raise RuntimeError(f"local adapter outcome uncertain: {exc}") from exc

    try:
        outcome = supervisor(envelope, on_propose, python_path=python_path)
        if not isinstance(outcome, dict) or outcome.get("attempt_id") != aid:
            raise ContractError("supervisor result attempt mismatch")
        checkpoint_id = outcome.get("checkpoint_id")
        if checkpoint_id is not None:
            try:
                checkpoint_name = str(uuid.UUID(checkpoint_id))
            except (ValueError, AttributeError, TypeError) as exc:
                raise ContractError("supervisor checkpoint ID is invalid") from exc
            checkpoint_path = attempt_dir / "checkpoints" / f"{checkpoint_name}.json"
            if not checkpoint_path.is_file() or checkpoint_path.is_symlink():
                raise ContractError("supervisor checkpoint is absent")
            validated_checkpoint_id = checkpoint_name
    except Exception as exc:
        failure = str(exc)
    snapshot = ledger.snapshot(aid)
    actions = snapshot["actions"]
    if any(a["status"] == "unknown" for a in actions):
        terminal = "unknown"
    elif failure:
        terminal = "failed"
    elif actions and all(a["status"] == "completed" for a in actions):
        terminal = "completed"
    elif actions and all(a["status"] == "denied" for a in actions):
        terminal = "denied"
    else:
        terminal = "failed"
    receipt_path = attempt_dir / "receipt.json"
    reason = "reconciliation_required" if terminal == "unknown" else failure
    receipt = {"schema_version": 1, "work_id": work_id, "attempt_id": aid, "envelope_digest": envelope_digest(envelope),
               "charter_digest": envelope["charter_digest"], "manifest_digest": envelope["manifest_digest"],
               "charter_sources": envelope["charter_sources"], "run_protocol_revision": envelope["run_protocol_revision"],
               "definition_digest": envelope["definition_digest"], "provider": envelope["provider"],
               "status": terminal, "reason": reason,
               "checkpoint_id": validated_checkpoint_id, "actions": actions, "created_at": utc_now()}
    validate_receipt(envelope, receipt)
    write_atomic(receipt_path, canonical(receipt) + "\n", mode=0o600)
    ledger.finish_attempt(aid, terminal, receipt["reason"], str(receipt_path))
    return {"attempt_id": aid, "status": terminal, "receipt_path": str(receipt_path), "reason": receipt["reason"]}
