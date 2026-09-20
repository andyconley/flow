"""Flow's application gateway for one supervised local MAF specialist call."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from pathlib import Path
from typing import Any, Callable

from execution_contracts import ContractError, canonical, digest, envelope_digest, validate_action, validate_receipt, validate_result, validate_replan
from execution_ledger import ExecutionLedger, utc_now
from fsutil import repo_root, write_atomic
from local_worker import call_local
from maf_supervisor import PINNED_MAF_CORE_VERSION, run_maf, run_maf_multiturn, run_maf_action3_continuation
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
            test_provider: str | None = None, execution_protocol_version: int = 1) -> tuple[dict[str, Any], Path, ExecutionLedger]:
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
    if execution_protocol_version == 2:
        envelope["execution_protocol_version"] = 2
    elif execution_protocol_version != 1:
        raise ContractError("unsupported execution protocol version")
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
        decision = ledger.decide(envelope, action, generation=1)
        if not decision["allowed"]:
            return {"status": "denied", "reason": decision["reason"], "action_id": action["action_id"]}
        if not ledger.consume_grant(action["action_id"], decision["grant_id"], generation=1):
            current = next((item for item in ledger.snapshot(aid)["actions"] if item["action_id"] == action["action_id"]), None)
            reason = current["reason"] if current and current["reason"] == "grant_expired" else "grant_reused"
            return {"status": "denied", "reason": reason, "action_id": action["action_id"]}
        with ledger.send_lock():
            ledger.assert_owner(aid, 1)
            try:
                ledger.observe_send(action["action_id"], 1)
                result = adapter(envelope)
                validate_result(envelope, result)
                ledger.observe_response(action["action_id"], result, 1)
                ledger.complete(action["action_id"], result, generation=1)
                return {"status": "completed", "action_id": action["action_id"], "output": result["output"]}
            except Exception as exc:
                ledger.mark_unknown(action["action_id"], "adapter_outcome_uncertain", generation=1)
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
            runtime_version = outcome.get("runtime_version")
            if not isinstance(runtime_version, str) or not runtime_version:
                raise ContractError("supervisor runtime version is absent")
            ledger.assert_owner(aid, 1)
            high_water = ledger.snapshot(aid)["events"][-1]["seq"]
            ledger.bind_checkpoint(aid, checkpoint_name, envelope_digest(envelope), high_water,
                                   1, runtime_version, str(checkpoint_path), generation=1)
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
    with ledger.send_lock():
        ledger.assert_owner(aid, 1)
        write_atomic(receipt_path, canonical(receipt) + "\n", mode=0o600)
        ledger.finish_attempt(aid, terminal, receipt["reason"], str(receipt_path), generation=1)
    return {"attempt_id": aid, "status": terminal, "receipt_path": str(receipt_path), "reason": receipt["reason"]}


def execute_multiturn_local(work_id: str, assignment_id: str, task_file: str, *, root: Path | None = None,
                            adapter: Callable[..., dict[str, Any]] | None = None,
                            python_path: str | None = None,
                            interrupt_after_third_send: bool = False,
                            _existing: tuple[dict[str, Any], Path, ExecutionLedger, int, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Run the bounded three-call exercise with Flow owning every decision."""
    if _existing is None:
        envelope, attempt_dir, ledger = prepare(
            work_id, assignment_id, task_file, root=root,
            test_provider="local-stub" if adapter is not None else None,
            execution_protocol_version=2,
        )
        generation, resume = 1, None
    else:
        envelope, attempt_dir, ledger, generation, resume = _existing
    physical_adapter = adapter is None
    adapter = adapter or call_local
    aid = envelope["attempt_id"]
    failure = ""

    def bind_prior(proposal: dict[str, Any]) -> None:
        # A pending next-position checkpoint is the MAF barrier *after* the
        # previous action's committed result. Flow binds that committed action,
        # not the new proposal, to the checkpoint.
        if proposal["kind"] != "replan" or proposal["sequence"] not in {1, 2}:
            return
        completed_action = proposal["sequence"]
        if any(p["kind"] == "delegate" and p["sequence"] == completed_action
               for p in ledger.snapshot(aid)["checkpoint_positions"]):
            return
        checkpoint_id = str(uuid.UUID(proposal["checkpoint_id"]))
        checkpoint_path = attempt_dir / "checkpoints" / f"{checkpoint_id}.json"
        snapshot = ledger.snapshot(aid)
        if not snapshot["events"]:
            raise ContractError("checkpoint has no Flow ledger barrier")
        ledger.bind_checkpoint_position(
            aid, "delegate", completed_action, checkpoint_id,
            envelope_digest(envelope), snapshot["events"][-1]["seq"],
            1, proposal["runtime_version"], str(checkpoint_path), generation=generation,
        )

    def on_action(proposal: dict[str, Any]) -> dict[str, Any]:
        validate_action(envelope, proposal)
        logical = {key: value for key, value in proposal.items()
                   if key not in {"checkpoint_id", "runtime_version"}}
        decision = ledger.decide(envelope, logical, generation=generation)
        if not decision["allowed"]:
            return {"status": "denied", "reason": decision["reason"], "action_id": proposal["action_id"]}
        if decision.get("replayed") and decision.get("result") is not None:
            return {"status": "completed", "action_id": proposal["action_id"],
                    "output": decision["result"]["output"], "replayed": True}
        if not decision.get("replayed"):
            checkpoint_id = str(uuid.UUID(proposal["checkpoint_id"]))
            checkpoint_path = attempt_dir / "checkpoints" / f"{checkpoint_id}.json"
            high_water = ledger.snapshot(aid)["events"][-1]["seq"]
            ledger.bind_checkpoint_position(
                aid, "pending_delegate", proposal["sequence"], checkpoint_id,
                envelope_digest(envelope), high_water, 1, proposal["runtime_version"],
                str(checkpoint_path), generation=generation,
            )
        if not ledger.consume_grant(proposal["action_id"], decision["grant_id"], generation=generation):
            raise ContractError("action grant was already consumed without a committed result")
        with ledger.send_lock():
            ledger.assert_owner(aid, generation)
            ledger.observe_send(proposal["action_id"], generation)
            if interrupt_after_third_send and proposal["sequence"] == 3:
                ledger.mark_unknown(proposal["action_id"], "controlled_post_send_interruption", generation=generation)
                raise RuntimeError("controlled post-send interruption")
            try:
                result = (call_local(envelope, correlation_id=proposal["action_id"])
                          if physical_adapter else adapter(envelope))
                validate_result(envelope, result)
                ledger.observe_response(proposal["action_id"], result, generation)
                ledger.complete(proposal["action_id"], result, generation=generation)
            except Exception as exc:
                ledger.mark_unknown(proposal["action_id"], "adapter_outcome_uncertain", generation=generation)
                raise RuntimeError(f"local adapter outcome uncertain: {exc}") from exc
        return {"status": "completed", "action_id": proposal["action_id"], "output": result["output"]}

    def on_replan(proposal: dict[str, Any]) -> dict[str, Any]:
        validate_replan(envelope, proposal)
        bind_prior(proposal)
        logical = {key: value for key, value in proposal.items()
                   if key not in {"checkpoint_id", "runtime_version"}}
        decision = ledger.decide_replan(envelope, logical, generation=generation)
        return {"status": "allowed" if decision["allowed"] else "denied",
                "reason": decision["reason"], "replan_id": proposal["replan_id"]}

    try:
        first = run_maf_multiturn(envelope, on_action, on_replan, phase="initial", python_path=python_path,
                                  resume=resume)
        snapshot = ledger.snapshot(aid)
        if (first.get("reason") != "denied_replan_cap" or
                [a["status"] for a in snapshot["actions"]] != ["completed", "completed"] or
                [r["status"] for r in snapshot["replans"]] != ["allowed", "allowed", "denied"]):
            raise ContractError("runtime_protocol_gap: initial phase did not reach the approved denial barrier")
        # This launch is an independent proposal, after Flow has checked that
        # the denial caused no replacement action or grant.
        run_maf_multiturn(envelope, on_action, on_replan, phase="action3", python_path=python_path)
    except Exception as exc:
        failure = str(exc)
    snapshot = ledger.snapshot(aid)
    actions = snapshot["actions"]
    terminal = "unknown" if any(a["status"] == "unknown" for a in actions) else (
        "completed" if not failure and len(actions) == 3 and all(a["status"] == "completed" for a in actions)
        else "failed"
    )
    reason = "reconciliation_required" if terminal == "unknown" else failure
    receipt_path = attempt_dir / "receipt.json"
    action_ids = {action["action_id"] for action in actions}
    sends = {event["action_id"] for event in snapshot["events"] if event["event"] == "adapter_send_started"}
    observer_path_raw = os.environ.get("FLOW_OLLAMA_OBSERVER_LOG")
    observer_rows: list[dict[str, Any]] | None = None
    if observer_path_raw:
        observer_path = Path(observer_path_raw).resolve()
        run_dir = attempt_dir.parent.parent
        if (not _inside(observer_path, run_dir.resolve()) or observer_path.is_symlink()
                or not observer_path.is_file() or observer_path.stat().st_size > 65536):
            raise ContractError("local observer evidence path is invalid")
        raw_rows = [json.loads(line) for line in observer_path.read_text().splitlines()]
        expected_fields = {"correlation_id", "arrival_time", "method", "path", "byte_count"}
        if any(not isinstance(row, dict) or set(row) != expected_fields for row in raw_rows):
            raise ContractError("local observer evidence has unexpected fields")
        observer_rows = [row for row in raw_rows if row["correlation_id"] in action_ids]
        if any(row["method"] != "POST" or row["path"] != "/api/chat" for row in observer_rows):
            raise ContractError("local observer evidence has an unexpected route")
        sealed = canonical(observer_rows) + "\n"
        write_atomic(attempt_dir / "endpoint-observations.json", sealed, mode=0o600)
    endpoint_evidence = {
        "status": "observed" if observer_rows is not None else "unavailable",
        "path": "endpoint-observations.json" if observer_rows is not None else None,
        "sha256": hashlib.sha256((canonical(observer_rows) + "\n").encode()).hexdigest() if observer_rows is not None else None,
        "actions": [
            {"action_id": action["action_id"], "flow_send_observed": action["action_id"] in sends,
             "endpoint_arrivals": sum(row["correlation_id"] == action["action_id"] for row in observer_rows)
             if observer_rows is not None else None}
            for action in actions
        ],
    }
    receipt = {
        "schema_version": 1, "execution_protocol_version": 2,
        "work_id": work_id, "attempt_id": aid, "envelope_digest": envelope_digest(envelope),
        "charter_digest": envelope["charter_digest"], "manifest_digest": envelope["manifest_digest"],
        "charter_sources": envelope["charter_sources"], "run_protocol_revision": envelope["run_protocol_revision"],
        "definition_digest": envelope["definition_digest"], "provider": envelope["provider"],
        "status": terminal, "reason": reason, "checkpoint_id": None,
        "actions": actions, "replans": snapshot["replans"],
        "checkpoints": snapshot["checkpoint_positions"], "created_at": utc_now(),
        "endpoint_evidence": endpoint_evidence,
    }
    validate_receipt(envelope, receipt)
    with ledger.send_lock():
        ledger.assert_owner(aid, generation)
        write_atomic(receipt_path, canonical(receipt) + "\n", mode=0o600)
        ledger.finish_attempt(aid, terminal, reason, str(receipt_path), generation=generation)
    return {"attempt_id": aid, "status": terminal, "receipt_path": str(receipt_path), "reason": reason}


def inspect_attempt(work_id: str, attempt_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """Read the original Flow evidence without starting a coordinator or adapter."""
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    execution_dir = run_dir / "execution"
    ledger_path = execution_dir / "ledger.sqlite"
    if not ledger_path.is_file() or not attempt_id or any(c not in "0123456789abcdef" for c in attempt_id):
        raise ContractError("execution attempt is absent or invalid")
    ledger = ExecutionLedger(ledger_path, read_only=True)
    snapshot = ledger.snapshot(attempt_id)
    if snapshot["work_id"] != work_id:
        raise ContractError("attempt belongs to a different work item")
    envelope = snapshot["envelope"]
    attempt_dir = execution_dir / attempt_id
    if not attempt_dir.is_dir() or attempt_dir.is_symlink():
        raise ContractError("attempt evidence directory is absent")
    sources = {}
    for name, expected in (("manifest.snapshot.json", envelope["manifest_digest"]),
                           ("requirements.snapshot.md", envelope["charter_sources"]["requirements"]["sha256"]),
                           ("acceptance.snapshot.md", envelope["charter_sources"]["acceptance"]["sha256"])):
        path = attempt_dir / name
        sources[name] = {"present": path.is_file() and not path.is_symlink(),
                         "matches": path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == expected}
    receipt_path = attempt_dir / "receipt.json"
    receipt = None
    if receipt_path.is_file() and not receipt_path.is_symlink():
        try:
            receipt = json.loads(receipt_path.read_text())
            validate_receipt(envelope, receipt)
        except (ValueError, OSError) as exc:
            raise ContractError(f"receipt is invalid: {exc}") from exc
    missing_evidence = [name for name, state in sources.items() if not state["matches"]]
    if snapshot.get("execution_protocol_version") == 2:
        for position in snapshot.get("checkpoint_positions", []):
            try:
                ledger.read_checkpoint_position(attempt_id, position["kind"], position["sequence"])
            except (ContractError, OSError, ValueError):
                missing_evidence.append(f"checkpoint:{position['kind']}:{position['sequence']}")
        endpoint = receipt.get("endpoint_evidence") if isinstance(receipt, dict) else None
        if isinstance(endpoint, dict) and endpoint.get("status") == "observed":
            endpoint_path = attempt_dir / "endpoint-observations.json"
            if (endpoint.get("path") != "endpoint-observations.json" or endpoint_path.is_symlink()
                    or not endpoint_path.is_file() or
                    hashlib.sha256(endpoint_path.read_bytes()).hexdigest() != endpoint.get("sha256")):
                missing_evidence.append("endpoint-observations.json")
            else:
                try:
                    rows = json.loads(endpoint_path.read_text())
                    sends = {event["action_id"] for event in snapshot["events"]
                             if event["event"] == "adapter_send_started"}
                    expected = [
                        {"action_id": action["action_id"],
                         "flow_send_observed": action["action_id"] in sends,
                         "endpoint_arrivals": sum(row["correlation_id"] == action["action_id"] for row in rows)}
                        for action in snapshot["actions"]
                    ]
                    if endpoint.get("actions") != expected:
                        missing_evidence.append("endpoint-observations.json:count-mismatch")
                except (TypeError, ValueError, KeyError):
                    missing_evidence.append("endpoint-observations.json:invalid")
    for resolution in snapshot.get("resolutions", []):
        for item in resolution["evidence"]:
            raw_path = project_root / item["path"]
            path = raw_path.resolve()
            if raw_path.is_symlink() or not _inside(path, attempt_dir) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                missing_evidence.append(item["path"])
    for epoch in snapshot.get("continuations", []):
        linked_path = epoch.get("receipt_path")
        if epoch.get("receipt_sha256") != (hashlib.sha256(receipt_path.read_bytes()).hexdigest() if receipt else None):
            missing_evidence.append(f"continuation:{epoch['epoch_id']}:original-receipt")
        if linked_path:
            linked = Path(linked_path)
            if (linked.is_symlink() or linked.parent != attempt_dir or not linked.is_file()):
                missing_evidence.append(f"continuation:{epoch['epoch_id']}:receipt")
            else:
                try:
                    linked_bytes = linked.read_bytes()
                    record = json.loads(linked_bytes)
                    if (record.get("epoch_id") != epoch["epoch_id"] or
                            record.get("original_receipt_sha256") != epoch["receipt_sha256"] or
                            record.get("status") != epoch["status"] or
                            hashlib.sha256(linked_bytes).hexdigest() != epoch.get("sealed_receipt_sha256")):
                        missing_evidence.append(f"continuation:{epoch['epoch_id']}:receipt")
                except (TypeError, ValueError, OSError):
                    missing_evidence.append(f"continuation:{epoch['epoch_id']}:receipt")
    return {"snapshot": snapshot, "sources": sources, "receipt": receipt,
            "missing_evidence": missing_evidence}


def resume_local(work_id: str, attempt_id: str, *, root: Path | None = None,
                 supervisor: Callable[..., dict[str, Any]] | None = None,
                 python_path: str | None = None,
                 adapter: Callable[..., dict[str, Any]] | None = None,
                 interrupt_after_third_send: bool = False) -> dict[str, Any]:
    """Fence the former coordinator and resume only a proved safe action."""
    inspected = inspect_attempt(work_id, attempt_id, root=root)
    snapshot = inspected["snapshot"]
    if snapshot.get("recovery_version") != 2 or inspected["missing_evidence"]:
        raise ContractError("historical or source-mismatched attempt cannot resume")
    envelope = snapshot["envelope"]
    attempt_dir = (root or repo_root()).resolve() / ".flow" / "runs" / work_id / "execution" / attempt_id
    if (attempt_dir / "envelope.json").read_text().strip() != canonical(envelope):
        raise ContractError("stored execution envelope differs from original snapshot")
    if inspected["receipt"] is not None and snapshot["receipt_path"] is None:
        receipt = inspected["receipt"]
        # The file was sealed before the terminal ledger update. Finish it
        # after fencing, without another child or provider invocation.
        ledger = ExecutionLedger(attempt_dir.parent / "ledger.sqlite")
        generation = ledger.claim_recovery(attempt_id)
        current = ledger.snapshot(attempt_id)
        if (receipt["actions"] != current["actions"] or current["status"] != "started"
                or (current.get("execution_protocol_version") == 2 and
                    (receipt.get("replans") != current["replans"] or
                     receipt.get("checkpoints") != current["checkpoint_positions"]))):
            raise ContractError("receipt actions or terminal state conflict with fenced ledger")
        expected = "completed" if current["actions"] and all(a["status"] == "completed" for a in current["actions"]) else "unknown" if any(a["status"] == "unknown" for a in current["actions"]) else "denied" if current["actions"] and all(a["status"] == "denied" for a in current["actions"]) else "failed"
        if receipt["status"] != expected:
            raise ContractError("receipt terminal status conflicts with fenced ledger")
        ledger.finish_attempt(attempt_id, receipt["status"], receipt.get("reason", ""),
                              str(attempt_dir / "receipt.json"), generation=generation)
        return {"attempt_id": attempt_id, "status": "repaired", "receipt_path": str(attempt_dir / "receipt.json")}
    if snapshot["status"] != "started":
        if snapshot["status"] == "unknown":
            return {"attempt_id": attempt_id, "status": "reconciliation_required",
                    "reason": "dispatch outcome uncertain"}
        return {"attempt_id": attempt_id, "status": "read_only", "reason": "attempt already terminal"}
    if snapshot.get("execution_protocol_version") == 2:
        actions = snapshot["actions"]
        if any(action["status"] in {"unknown", "started"} for action in actions):
            # Fence a former parent and turn any started send into unknown.
            ledger = ExecutionLedger(attempt_dir.parent / "ledger.sqlite")
            generation = ledger.claim_recovery(attempt_id)
            return {"attempt_id": attempt_id, "status": "reconciliation_required",
                    "reason": "dispatch outcome uncertain", "owner_generation": generation}
        completed = [action for action in actions if action["status"] == "completed"]
        if not completed or len(completed) > 2 or [a["request"]["sequence"] for a in completed] != list(range(1, len(completed) + 1)):
            return {"attempt_id": attempt_id, "status": "runtime_protocol_gap",
                    "reason": "no replayable v2 committed action prefix"}
        last = completed[-1]
        if last["result"] is None:
            return {"attempt_id": attempt_id, "status": "runtime_protocol_gap",
                    "reason": "committed action has no durable result"}
        validate_result(envelope, last["result"])
        ledger = ExecutionLedger(attempt_dir.parent / "ledger.sqlite")
        try:
            pending = ledger.read_checkpoint_position(attempt_id, "pending_delegate", last["request"]["sequence"])
        except (ContractError, OSError, ValueError) as exc:
            return {"attempt_id": attempt_id, "status": "runtime_protocol_gap",
                    "reason": f"pending MAF checkpoint cannot be verified: {exc}"}
        if pending["metadata"]["format_version"] != 1 or pending["metadata"]["runtime_version"] != PINNED_MAF_CORE_VERSION:
            return {"attempt_id": attempt_id, "status": "runtime_protocol_gap",
                    "reason": "pending MAF checkpoint runtime or format version is incompatible"}
        generation = ledger.claim_recovery(attempt_id)
        fenced = ledger.snapshot(attempt_id)
        if any(action["status"] == "unknown" for action in fenced["actions"]):
            return {"attempt_id": attempt_id, "status": "reconciliation_required",
                    "reason": "dispatch outcome uncertain", "owner_generation": generation}
        seq = last["request"]["sequence"]
        resume = {"checkpoint_id": pending["metadata"]["checkpoint_id"],
                  "request_id": f"flow-action-{seq}", "type": "action_result",
                  "action_id": last["action_id"], "kind": "delegate", "sequence": seq,
                  "result": {"status": "completed", "action_id": last["action_id"],
                             "output": last["result"]["output"], "replayed": True}}
        return execute_multiturn_local(work_id, envelope["assignment_id"], "", root=root,
                                       python_path=python_path, adapter=adapter,
                                       interrupt_after_third_send=interrupt_after_third_send,
                                       _existing=(envelope, attempt_dir, ledger, generation, resume))
    ledger = ExecutionLedger(attempt_dir.parent / "ledger.sqlite")
    generation = ledger.claim_recovery(attempt_id)
    snapshot = ledger.snapshot(attempt_id)
    actions = snapshot["actions"]
    if any(action["status"] in {"unknown", "started"} for action in actions):
        return {"attempt_id": attempt_id, "status": "reconciliation_required", "reason": "dispatch outcome uncertain", "owner_generation": generation}
    if not actions or actions[0]["status"] != "completed" or actions[0]["result"] is None:
        return {"attempt_id": attempt_id, "status": "reconciliation_required", "reason": "no replayable committed result", "owner_generation": generation}
    validate_result(envelope, actions[0]["result"])
    observations = [item for item in snapshot.get("response_observations", []) if item["action_id"] == actions[0]["action_id"]]
    if len(observations) != 1 or observations[0]["result"] != actions[0]["result"] or digest(observations[0]["result"]) != observations[0]["result_digest"]:
        raise ContractError("committed result differs from durable response observation")
    checkpoint = snapshot.get("checkpoint")
    if not isinstance(checkpoint, dict) or checkpoint.get("format_version") != 1 or checkpoint.get("envelope_digest") != envelope_digest(envelope):
        raise ContractError("compatible Flow checkpoint link is absent")
    if checkpoint.get("ledger_seq") not in {event["seq"] for event in snapshot["events"]}:
        raise ContractError("bound checkpoint ledger barrier is absent")
    try:
        checkpoint_name = str(uuid.UUID(checkpoint["checkpoint_id"]))
    except (TypeError, ValueError, KeyError) as exc:
        raise ContractError("bound MAF checkpoint ID is invalid") from exc
    if checkpoint_name != checkpoint["checkpoint_id"]:
        raise ContractError("bound MAF checkpoint ID is not canonical")
    checkpoint_path = attempt_dir / "checkpoints" / f"{checkpoint_name}.json"
    if checkpoint_path.is_symlink() or not checkpoint_path.is_file() or str(checkpoint_path) != checkpoint.get("path"):
        raise ContractError("bound MAF checkpoint is absent or foreign")
    try:
        checkpoint_bytes = checkpoint_path.read_bytes()
        if hashlib.sha256(checkpoint_bytes).hexdigest() != checkpoint.get("file_sha256"):
            raise ContractError("bound MAF checkpoint digest mismatch")
        json.loads(checkpoint_bytes)
    except (OSError, ValueError) as exc:
        raise ContractError("bound MAF checkpoint is corrupt") from exc

    def replay(action: dict[str, Any]) -> dict[str, Any]:
        ledger.assert_owner(attempt_id, generation)
        validate_action(envelope, action)
        if action != actions[0]["request"]:
            raise ContractError("recovery proposal differs from committed action")
        return {"status": "completed", "action_id": action["action_id"], "output": actions[0]["result"]["output"]}

    outcome = (supervisor or run_maf)(envelope, replay, python_path=python_path,
                                       resume={"schema_version": 2, "attempt_id": attempt_id,
                                               "checkpoint_id": checkpoint["checkpoint_id"],
                                               "ledger_seq": checkpoint["ledger_seq"],
                                               "runtime_version": checkpoint["runtime_version"]})
    ledger.assert_owner(attempt_id, generation)
    if outcome.get("attempt_id") != attempt_id:
        raise ContractError("recovered supervisor attempt mismatch")
    receipt = {"schema_version": 1, "work_id": work_id, "attempt_id": attempt_id,
               "envelope_digest": envelope_digest(envelope), "charter_digest": envelope["charter_digest"],
               "manifest_digest": envelope["manifest_digest"], "charter_sources": envelope["charter_sources"],
               "run_protocol_revision": envelope["run_protocol_revision"], "definition_digest": envelope["definition_digest"],
               "provider": envelope["provider"], "status": "completed", "reason": "",
               "checkpoint_id": checkpoint_name, "actions": ledger.snapshot(attempt_id)["actions"], "created_at": utc_now()}
    validate_receipt(envelope, receipt)
    receipt_path = attempt_dir / "receipt.json"
    with ledger.send_lock():
        ledger.assert_owner(attempt_id, generation)
        write_atomic(receipt_path, canonical(receipt) + "\n", mode=0o600)
        ledger.finish_attempt(attempt_id, "completed", "", str(receipt_path), generation=generation)
    return {"attempt_id": attempt_id, "status": "replayed", "owner_generation": generation,
            "checkpoint_id": checkpoint["checkpoint_id"], "result": actions[0]["result"], "receipt_path": str(receipt_path)}


def resolve_attempt(work_id: str, attempt_id: str, action_id: str, actor: str,
                    disposition: str, explanation: str, evidence_file: str,
                    *, root: Path | None = None) -> dict[str, Any]:
    """Record an operator decision only against immutable, local evidence."""
    inspected = inspect_attempt(work_id, attempt_id, root=root)
    snapshot = inspected["snapshot"]
    if snapshot.get("recovery_version") != 2 or inspected["missing_evidence"]:
        raise ContractError("historical or source-mismatched attempt cannot be resolved")
    if not isinstance(actor, str) or not actor.strip():
        raise ContractError("operator identity is required")
    project_root = (root or repo_root()).resolve()
    attempt_dir = project_root / ".flow" / "runs" / work_id / "execution" / attempt_id
    evidence_input = Path(evidence_file)
    if evidence_input.is_symlink():
        raise ContractError("resolution evidence must not be a symlink")
    evidence_path = evidence_input.resolve()
    if not _inside(evidence_path, attempt_dir) or not evidence_path.is_file():
        raise ContractError("resolution evidence must be an existing attempt-local file")
    evidence = json.loads(evidence_path.read_text())
    if not isinstance(evidence, list) or not evidence:
        raise ContractError("resolution evidence file must contain a nonempty list")
    evidence_dir = attempt_dir / "resolution-evidence"
    if evidence_dir.is_symlink():
        raise ContractError("resolution evidence directory must not be a symlink")
    evidence_dir.mkdir(mode=0o700, exist_ok=True)
    if evidence_dir.is_symlink() or not _inside(evidence_dir.resolve(), attempt_dir):
        raise ContractError("resolution evidence directory is outside attempt")
    os.chmod(evidence_dir, 0o700)
    preserved = []
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ContractError("resolution evidence item is invalid")
        raw_path = project_root / item["path"]
        if raw_path.is_symlink():
            raise ContractError("resolution evidence source must not be a symlink")
        path = raw_path.resolve()
        if not _inside(path, attempt_dir) or not path.is_file() or path == evidence_path:
            raise ContractError("resolution evidence source is missing or outside attempt")
        content = path.read_bytes()
        if len(content) > 65536 or hashlib.sha256(content).hexdigest() != item.get("sha256"):
            raise ContractError("resolution evidence digest mismatch")
        proof_path = evidence_dir / f"{item['sha256']}.proof"
        if proof_path.exists():
            if proof_path.is_symlink() or proof_path.read_bytes() != content:
                raise ContractError("preserved resolution evidence conflicts with source")
        else:
            try:
                _write_snapshot(proof_path, content)
            except FileExistsError:
                if proof_path.is_symlink() or proof_path.read_bytes() != content:
                    raise ContractError("preserved resolution evidence conflicts with source")
            os.chmod(proof_path, 0o400)
        preserved.append({"kind": item.get("kind"), "path": str(proof_path.relative_to(project_root)), "sha256": item["sha256"]})
    ledger = ExecutionLedger(attempt_dir.parent / "ledger.sqlite")
    generation = ledger.claim_recovery(attempt_id, actor)
    return ledger.resolve_unknown(attempt_id, action_id, actor, disposition, explanation, preserved,
                                  generation=generation)


def continue_resolved_local(work_id: str, attempt_id: str, action_id: str, actor: str,
                            *, root: Path | None = None, python_path: str | None = None,
                            adapter: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    """Finish the resolved third action through a separately fenced epoch.

    Flow retains the original terminal attempt and receipt. The MAF child only
    confirms that the exact checkpointed action is pending and accepts a
    Flow-supplied response; it never decides whether another send is allowed.
    """
    if not isinstance(actor, str) or not actor.strip() or len(actor.encode()) > 256:
        raise ContractError("continuation actor is invalid")
    inspected = inspect_attempt(work_id, attempt_id, root=root)
    snapshot, receipt = inspected["snapshot"], inspected["receipt"]
    if inspected["missing_evidence"] or snapshot.get("execution_protocol_version") != 2:
        raise ContractError("continuation evidence is missing or incompatible")
    if not isinstance(receipt, dict) or snapshot["status"] not in {"unknown", "failed"}:
        raise ContractError("continuation requires an original terminal receipt")
    envelope = snapshot["envelope"]
    project_root = (root or repo_root()).resolve()
    attempt_dir = project_root / ".flow" / "runs" / work_id / "execution" / attempt_id
    receipt_path = attempt_dir / "receipt.json"
    ledger_path = attempt_dir.parent / "ledger.sqlite"
    for protected in (attempt_dir, receipt_path, ledger_path):
        mode = protected.lstat()
        if (stat.S_ISLNK(mode.st_mode) or mode.st_uid != os.getuid()
                or mode.st_mode & (stat.S_IRWXG | stat.S_IRWXO)):
            raise ContractError("continuation requires owner-only local evidence")
    if snapshot["receipt_path"] != str(receipt_path) or receipt_path.is_symlink():
        raise ContractError("original terminal receipt path differs from ledger")
    original_receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    if (receipt.get("attempt_id") != attempt_id or receipt.get("status") != snapshot["status"]
            or receipt.get("envelope_digest") != envelope_digest(envelope)):
        raise ContractError("original receipt identity differs from ledger")
    actions = [a for a in snapshot["actions"] if a["action_id"] == action_id]
    resolutions = [r for r in snapshot["resolutions"] if r["action_id"] == action_id]
    if len(actions) != 1 or len(resolutions) != 1 or actions[0]["request"]["sequence"] != 3:
        raise ContractError("continuation requires exactly one resolved third action")
    action, resolution = actions[0], resolutions[0]
    resolution_record = {key: resolution[key] for key in
                         ("action_id", "actor", "disposition", "evidence", "explanation")}
    resolution_record["attempt_id"] = attempt_id
    if digest(resolution_record) != resolution["resolution_digest"]:
        raise ContractError("continuation resolution digest mismatch")
    disposition = resolution["disposition"]
    if disposition not in {"resolved_completed", "resolved_not_dispatched"}:
        raise ContractError("resolution does not permit continuation")
    if disposition == "resolved_completed":
        if snapshot["status"] != "unknown" or action["status"] != "completed" or action["result"] != resolution["result"]:
            raise ContractError("completed resolution has no matching durable result")
        observed = [o for o in snapshot["response_observations"] if o["action_id"] == action_id]
        if len(observed) != 1 or observed[0]["result"] != action["result"] or digest(observed[0]["result"]) != observed[0]["result_digest"]:
            raise ContractError("completed result lacks matching response observation")
    elif snapshot["status"] != "failed" or action["status"] != "not_dispatched":
        raise ContractError("no-dispatch resolution differs from terminal action")
    validate_action(envelope, action["request"])
    ledger = ExecutionLedger(ledger_path)
    pending = ledger.read_checkpoint_position(attempt_id, "pending_delegate", 3)
    checkpoint = pending["metadata"]
    if checkpoint["runtime_version"] != PINNED_MAF_CORE_VERSION or checkpoint["format_version"] != 1:
        raise ContractError("pending checkpoint uses an incompatible MAF runtime")
    barrier = [e for e in snapshot["events"] if e["seq"] == checkpoint["ledger_seq"]]
    if len(barrier) != 1 or barrier[0]["action_id"] != action_id or barrier[0]["event"] != "policy_allowed":
        raise ContractError("pending checkpoint does not follow original policy allowance")
    if (attempt_dir / "envelope.json").read_text().strip() != canonical(envelope):
        raise ContractError("original envelope differs from snapshot")
    epoch = ledger.begin_continuation(attempt_id, action_id, resolution["resolution_id"],
                                      original_receipt_sha, checkpoint["file_sha256"], actor=actor)
    epoch_id = epoch["epoch_id"]
    generation = ledger.claim_continuation(epoch_id, actor=actor)
    if ledger.continuation_snapshot(epoch_id)["status"] == "unknown":
        unknown_reason = "previous continuation send outcome uncertain"
        linked_path = attempt_dir / f"continuation-{epoch_id}.json"
        unknown_receipt = {"schema_version": 1, "kind": "continuation_receipt",
                           "work_id": work_id, "attempt_id": attempt_id, "action_id": action_id,
                           "epoch_id": epoch_id, "owner_generation": generation,
                           "original_receipt_sha256": original_receipt_sha,
                           "resolution_id": resolution["resolution_id"],
                           "resolution_digest": resolution["resolution_digest"],
                           "checkpoint_id": checkpoint["checkpoint_id"],
                           "checkpoint_sha256": checkpoint["file_sha256"],
                           "status": "unknown", "reason": unknown_reason,
                           "maf_acknowledgment": None,
                           "policy_counters": ledger.continuation_policy_counters(epoch_id, terminal_status="unknown"),
                           "grant": ledger.continuation_snapshot(epoch_id)["grant"],
                           "response_digest": None, "created_at": utc_now()}
        with ledger.send_lock():
            if ledger.continuation_snapshot(epoch_id)["owner_generation"] != generation:
                raise ContractError("continuation owner is stale before unknown receipt seal")
            write_atomic(linked_path, canonical(unknown_receipt) + "\n", mode=0o600)
            ledger.seal_unknown_continuation(epoch_id, str(linked_path), generation=generation)
        return {"attempt_id": attempt_id, "action_id": action_id, "epoch_id": epoch_id,
                "status": "unknown", "reason": unknown_reason,
                "receipt_path": str(linked_path)}

    def verify_current() -> None:
        current = inspect_attempt(work_id, attempt_id, root=root)
        if current["missing_evidence"] or hashlib.sha256(receipt_path.read_bytes()).hexdigest() != original_receipt_sha:
            raise ContractError("continuation evidence changed")
        current_resolution = [r for r in current["snapshot"]["resolutions"] if r["resolution_id"] == resolution["resolution_id"]]
        if len(current_resolution) != 1 or current_resolution[0] != resolution:
            raise ContractError("continuation resolution changed")
        current_checkpoint = ledger.read_checkpoint_position(attempt_id, "pending_delegate", 3)["metadata"]
        if current_checkpoint != checkpoint:
            raise ContractError("continuation checkpoint changed")
        if current["snapshot"]["envelope"] != envelope:
            raise ContractError("continuation envelope changed")
        current_action = [a for a in current["snapshot"]["actions"] if a["action_id"] == action_id]
        if len(current_action) != 1 or current_action[0] != action:
            raise ContractError("continuation action changed")

    def on_ready(proposal: dict[str, Any]) -> dict[str, Any]:
        verify_current()
        validate_action(envelope, proposal)
        if proposal["action_id"] != action_id or proposal["sequence"] != 3 or proposal["request_id"] != "flow-action-3":
            raise ContractError("restored MAF request differs from resolved action")
        if disposition == "resolved_completed":
            ledger.observe_continuation_response(epoch_id, action["result"], generation=generation)
            return {"status": "completed", "action_id": action_id,
                    "output": action["result"]["output"], "replayed": True}
        with ledger.send_lock():
            verify_current()
            decision = ledger.regrant_continuation(epoch_id, envelope, action["request"], generation=generation)
            if not decision["allowed"]:
                raise ContractError("continuation policy denied: " + decision["reason"])
            if not ledger.claim_continuation_send(epoch_id, decision["grant_id"], generation=generation):
                raise ContractError("continuation send claim was already consumed")
            physical = adapter or call_local
            try:
                result = (physical(envelope, correlation_id=action_id) if adapter is None else physical(envelope))
                validate_result(envelope, result)
                ledger.observe_continuation_response(epoch_id, result, generation=generation)
            except Exception:
                # The claim crossed Flow's send boundary. Its outcome is now
                # uncertain even when the adapter raised before returning.
                raise
            return {"status": "completed", "action_id": action_id, "output": result["output"]}

    status, reason = "failed", ""
    acknowledgment: dict[str, Any] | None = None
    try:
        verify_current()
        acknowledgment = run_maf_action3_continuation(
            envelope, {"schema_version": 2, "checkpoint_id": checkpoint["checkpoint_id"],
                       "request_id": "flow-action-3", "action_id": action_id},
            on_ready, python_path=python_path,
        )
        if acknowledgment.get("reason") != "action-3-complete":
            raise ContractError("MAF did not acknowledge the resolved third action")
        status = "completed"
    except Exception as exc:
        reason = str(exc)
        latest = ledger.continuation_snapshot(epoch_id)
        if latest.get("send_claimed"):
            status = "unknown"
    linked = {"schema_version": 1, "kind": "continuation_receipt", "attempt_id": attempt_id,
              "work_id": work_id, "action_id": action_id, "epoch_id": epoch_id,
              "owner_generation": generation, "original_receipt_sha256": original_receipt_sha,
              "resolution_id": resolution["resolution_id"], "resolution_digest": resolution["resolution_digest"],
              "checkpoint_id": checkpoint["checkpoint_id"], "checkpoint_sha256": checkpoint["file_sha256"],
              "status": status, "reason": reason, "maf_acknowledgment": acknowledgment,
              "policy_counters": ledger.continuation_policy_counters(epoch_id, terminal_status=status),
              "grant": ledger.continuation_snapshot(epoch_id)["grant"],
              "response_digest": (ledger.continuation_snapshot(epoch_id)["response"] or {}).get("result_digest"),
              "created_at": utc_now()}
    linked_path = attempt_dir / f"continuation-{epoch_id}.json"
    with ledger.send_lock():
        if ledger.continuation_snapshot(epoch_id)["owner_generation"] != generation:
            raise ContractError("continuation owner is stale before receipt seal")
        write_atomic(linked_path, canonical(linked) + "\n", mode=0o600)
        ledger.finish_continuation(epoch_id, status, reason, str(linked_path), generation=generation)
    return {"attempt_id": attempt_id, "action_id": action_id, "epoch_id": epoch_id,
            "status": status, "reason": reason, "receipt_path": str(linked_path)}
