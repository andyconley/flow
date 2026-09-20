"""Flow-owned v4 gateway for one local plan and one Claude code review."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable

from claude_worker import build_prompt, call_claude
from execution_contracts import ContractError, canonical, digest, envelope_digest, validate_action, validate_receipt, validate_result
from execution_gateway import _effective_specialist_for, _inside, _run_file, _write_snapshot
from execution_ledger import ExecutionLedger, utc_now
from fsutil import repo_root, write_atomic
from local_worker import call_local
from maf_supervisor import PINNED_MAF_CORE_VERSION, run_maf_claude
from orchestration import validate_orchestration
from runstate import status as run_status

SOURCE_COMMIT = "971bba4452d7e988e77107f6b08b2e96991bd660"
SOURCE_PATHS = ("cli/codex_worker.py", "tests/test_codex_worker.py")


def _source_blob(project_root: Path, relative: str) -> bytes:
    tree = subprocess.run(["git", "ls-tree", SOURCE_COMMIT, "--", relative], cwd=project_root,
                          capture_output=True, check=True)
    if not tree.stdout.startswith(b"100644 blob ") or len(tree.stdout.splitlines()) != 1:
        raise ContractError("approved Claude review source is not a regular Git blob")
    blob = subprocess.run(["git", "show", f"{SOURCE_COMMIT}:{relative}"], cwd=project_root,
                          capture_output=True, check=True).stdout
    if not blob or len(blob) > 16384:
        raise ContractError("approved Claude review source is empty or too large")
    return blob


def prepare_claude(work_id: str, local_task_file: str, claude_task_file: str, *,
                   root: Path | None = None) -> tuple[dict[str, Any], Path, ExecutionLedger]:
    """Snapshot approved sources and create a v4 attempt before any provider send."""
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    state = run_status(work_id, root=project_root)
    if state.get("state") != "implementing" or state.get("protocol_revision") != 2:
        raise ContractError("Claude execution requires an implementing revision-2 run")
    valid, _, findings = validate_orchestration(work_id, "dispatch", root=project_root)
    if not valid:
        raise ContractError("orchestration dispatch invalid: " + "; ".join(f.message for f in findings))
    manifest_path = run_dir / "orchestration.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    names = ("local-worker", "claude-worker")
    roles = ("test-engineer", "quality-reviewer")
    providers = ("ollama", "claude")
    task_paths = (_run_file(project_root, run_dir, local_task_file),
                  _run_file(project_root, run_dir, claude_task_file))
    assignments: list[dict[str, Any]] = []
    for sequence, (assignment_id, role, provider, task_path) in enumerate(zip(names, roles, providers, task_paths), 1):
        matches = [item for item in manifest["assignments"] if item.get("id") == assignment_id]
        if len(matches) != 1 or matches[0].get("role") != role:
            raise ContractError(f"approved {role} assignment not found")
        execution = matches[0].get("execution")
        if not isinstance(execution, dict) or execution.get("provider") != provider or not isinstance(execution.get("model"), str) or not execution["model"].strip():
            raise ContractError(f"approved {provider} execution settings are absent")
        task = task_path.read_text()
        if not task.strip() or len(task.encode()) > 4096:
            raise ContractError("Claude review task is empty or too large")
        instructions = _effective_specialist_for(role)
        assignments.append({"sequence": sequence, "assignment_id": assignment_id,
                            "role": role, "provider": provider, "model": execution["model"],
                            "instance_id": f"{role}-1", "definition_digest": digest({"role": role, "instructions": instructions}),
                            "instructions": instructions, "task": task,
                            "task_digest": hashlib.sha256(task.encode()).hexdigest()})
    artifacts = state.get("artifacts", {})
    requirements = _run_file(project_root, run_dir, artifacts.get("requirements", ""))
    acceptance = _run_file(project_root, run_dir, artifacts.get("acceptance_criteria", ""))
    requirements_bytes, acceptance_bytes = requirements.read_bytes(), acceptance.read_bytes()
    source_blobs = {relative: _source_blob(project_root, relative) for relative in SOURCE_PATHS}
    source_files = [{"path": relative, "sha256": hashlib.sha256(source_blobs[relative]).hexdigest()}
                    for relative in SOURCE_PATHS]
    attempt_id = uuid.uuid4().hex
    execution_dir = run_dir / "execution"
    execution_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(execution_dir, 0o700)
    attempt_dir = execution_dir / attempt_id
    attempt_dir.mkdir(mode=0o700)
    (attempt_dir / "checkpoints").mkdir(mode=0o700)
    source_dir = attempt_dir / "source"
    source_dir.mkdir(mode=0o700)
    for relative, blob in source_blobs.items():
        target = source_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_snapshot(target, blob)
    for source_bytes, name in ((manifest_bytes, "manifest.snapshot.json"),
                               (requirements_bytes, "requirements.snapshot.md"),
                               (acceptance_bytes, "acceptance.snapshot.md")):
        _write_snapshot(attempt_dir / name, source_bytes)
    if (manifest_path.read_bytes() != manifest_bytes or requirements.read_bytes() != requirements_bytes
            or acceptance.read_bytes() != acceptance_bytes):
        raise ContractError("approved Claude execution sources changed during preparation")
    envelope = {"schema_version": 1, "execution_protocol_version": 4,
                "work_id": work_id, "attempt_id": attempt_id,
                "charter_digest": digest({"requirements": hashlib.sha256(requirements_bytes).hexdigest(),
                                          "acceptance": hashlib.sha256(acceptance_bytes).hexdigest()}),
                "charter_sources": {"requirements": {"path": str(requirements.relative_to(project_root)), "sha256": hashlib.sha256(requirements_bytes).hexdigest()},
                                    "acceptance": {"path": str(acceptance.relative_to(project_root)), "sha256": hashlib.sha256(acceptance_bytes).hexdigest()}},
                "run_protocol_revision": 2, "manifest_digest": hashlib.sha256(manifest_bytes).hexdigest(),
                "assignments": assignments, "source_commit": SOURCE_COMMIT, "source_files": source_files,
                "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "max_claude_calls": 1},
                "checkpoint_dir": str(attempt_dir / "checkpoints")}
    envelope_digest(envelope)
    write_atomic(attempt_dir / "envelope.json", canonical(envelope) + "\n", mode=0o600)
    ledger = ExecutionLedger(execution_dir / "ledger.sqlite")
    ledger.create_attempt(envelope)
    return envelope, attempt_dir, ledger


def _claude_task(envelope: dict[str, Any], attempt_dir: Path, plan: str) -> str:
    source_dir = attempt_dir / "source"
    parts = [envelope["assignments"][1]["task"],
             f"Reviewed source commit: {envelope['source_commit']}",
             f"Local test plan SHA-256: {hashlib.sha256(plan.encode()).hexdigest()}",
             "Local test plan:\n" + plan]
    for item in envelope["source_files"]:
        path = source_dir / item["path"]
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ContractError("Claude review source snapshot changed")
        parts.append(f"Source {item['path']} SHA-256 {item['sha256']}:\n{path.read_text()}")
    parts.append("Review the supplied source only. Cite file names and the commit, classify any findings by severity, and say explicitly if you find none. Do not claim a full repository audit. Keep the review under 4 KiB.")
    return "\n\n".join(parts)


def execute_claude(work_id: str, local_task_file: str, claude_task_file: str, *, root: Path | None = None,
                   local_adapter: Callable[..., dict[str, Any]] | None = None,
                   claude_adapter: Callable[..., dict[str, Any]] | None = None,
                   supervisor: Callable[..., dict[str, Any]] | None = None,
                   python_path: str | None = None) -> dict[str, Any]:
    envelope, attempt_dir, ledger = prepare_claude(work_id, local_task_file, claude_task_file, root=root)
    aid = envelope["attempt_id"]
    local_adapter = local_adapter or call_local
    claude_adapter = claude_adapter or call_claude
    failure = ""
    review_artifact: dict[str, str] | None = None
    proposal_count = 0

    def on_action(proposal: dict[str, Any]) -> dict[str, Any]:
        nonlocal review_artifact, proposal_count
        proposal_count += 1
        if proposal_count > 2 or proposal.get("sequence") != proposal_count:
            raise ContractError("Claude coordinator proposed an extra or out-of-order action")
        logical = {key: value for key, value in proposal.items()
                   if key not in {"checkpoint_id", "runtime_version", "request_id"}}
        validate_action(envelope, logical)
        sequence = logical["sequence"]
        assignment = envelope["assignments"][sequence - 1]
        decision = ledger.decide(envelope, logical, generation=1)
        if not decision["allowed"]:
            return {"status": "denied", "reason": decision["reason"], "action_id": logical["action_id"]}
        try:
            checkpoint_id = str(uuid.UUID(proposal["checkpoint_id"]))
            checkpoint_path = attempt_dir / "checkpoints" / f"{checkpoint_id}.json"
            if checkpoint_path.is_symlink() or not checkpoint_path.is_file() or proposal["runtime_version"] != PINNED_MAF_CORE_VERSION:
                raise ContractError("Claude MAF checkpoint is absent or incompatible")
            high_water = ledger.snapshot(aid)["events"][-1]["seq"]
            ledger.bind_checkpoint_position(aid, "pending_delegate", sequence, checkpoint_id,
                                            envelope_digest(envelope), high_water, 1, proposal["runtime_version"],
                                            str(checkpoint_path), generation=1)
            if not ledger.consume_grant(logical["action_id"], decision["grant_id"], generation=1):
                raise ContractError("Claude grant was already consumed or expired")
        except Exception:
            current = next((item for item in ledger.snapshot(aid)["actions"]
                            if item["action_id"] == logical["action_id"]), None)
            if current and current["status"] == "allowed":
                ledger.close_pre_send_failure(logical["action_id"], decision["grant_id"], generation=1)
            raise
        with ledger.send_lock():
            ledger.assert_owner(aid, 1)
            ledger.observe_send(logical["action_id"], 1)
            try:
                if sequence == 1:
                    result = local_adapter({**assignment, "attempt_id": aid}, correlation_id=logical["action_id"])
                else:
                    plan_path = attempt_dir / "test-plan.md"
                    if plan_path.is_symlink() or not plan_path.is_file():
                        raise ContractError("local test plan is absent")
                    plan = plan_path.read_text()
                    task = _claude_task(envelope, attempt_dir, plan)
                    expected_input = hashlib.sha256(build_prompt(assignment["instructions"], task)).hexdigest()
                    result = claude_adapter(instructions=assignment["instructions"], task=task,
                                            workspace=attempt_dir / "source", model=assignment["model"],
                                            timeout_seconds=120)
                    validate_result(envelope, result, action=logical)
                    ledger.observe_response(logical["action_id"], result, 1)
                    if result.get("input_sha256") != expected_input:
                        raise ContractError("Claude provider input differs from sealed review package")
                    for item in envelope["source_files"]:
                        path = attempt_dir / "source" / item["path"]
                        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                            raise ContractError("Claude review source changed during provider call")
                    review_bytes = (result["output"] + "\n").encode()
                    _write_snapshot(attempt_dir / "review-output.md", review_bytes)
                    review_artifact = {"path": "review-output.md", "sha256": hashlib.sha256(review_bytes).hexdigest(),
                                       "plan_sha256": hashlib.sha256(plan.encode()).hexdigest()}
                if sequence == 1:
                    validate_result(envelope, result, action=logical)
                    ledger.observe_response(logical["action_id"], result, 1)
                ledger.complete(logical["action_id"], result, generation=1)
                if sequence == 1:
                    write_atomic(attempt_dir / "test-plan.md", result["output"], mode=0o600)
            except Exception as exc:
                ledger.mark_unknown(logical["action_id"], "adapter_outcome_uncertain", generation=1)
                raise RuntimeError(f"Claude job adapter outcome uncertain: {exc}") from exc
        return {"status": "completed", "action_id": logical["action_id"],
                "summary": result["output"], "output": result["output"]}

    try:
        outcome = (supervisor or run_maf_claude)(envelope, on_action, python_path=python_path)
        if outcome.get("attempt_id") != aid or outcome.get("reason") != "mixed-job-complete":
            raise ContractError("Claude supervisor did not finish the approved attempt")
    except Exception as exc:
        failure = str(exc)
    snapshot = ledger.snapshot(aid)
    for item in snapshot["actions"]:
        if item["status"] == "started":
            ledger.mark_unknown(item["action_id"], "dispatch_outcome_uncertain", generation=1)
    snapshot = ledger.snapshot(aid)
    actions = snapshot["actions"]
    terminal = "unknown" if any(item["status"] == "unknown" for item in actions) else (
        "completed" if not failure and len(actions) == 2 and all(item["status"] == "completed" for item in actions)
        else "failed")
    reason = "reconciliation_required" if terminal == "unknown" else failure
    receipt = {"schema_version": 1, "execution_protocol_version": 4, "work_id": work_id, "attempt_id": aid,
               "envelope_digest": envelope_digest(envelope), "charter_digest": envelope["charter_digest"],
               "manifest_digest": envelope["manifest_digest"], "charter_sources": envelope["charter_sources"],
               "run_protocol_revision": 2, "assignments": envelope["assignments"],
               "source_commit": envelope["source_commit"], "source_files": envelope["source_files"],
               "status": terminal, "reason": reason, "actions": actions, "replans": [],
               "checkpoints": snapshot.get("checkpoint_positions", []),
               "review_artifact": review_artifact, "failure_detail": failure[:512], "created_at": utc_now()}
    validate_receipt(envelope, receipt)
    receipt_path = attempt_dir / "receipt.json"
    with ledger.send_lock():
        ledger.assert_owner(aid, 1)
        write_atomic(receipt_path, canonical(receipt) + "\n", mode=0o600)
        ledger.finish_attempt(aid, terminal, reason, str(receipt_path), generation=1)
    return {"attempt_id": aid, "status": terminal, "receipt_path": str(receipt_path), "reason": reason}
