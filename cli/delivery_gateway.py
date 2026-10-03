"""Flow-owned dispatch boundary for a stock Magentic Delivery Lead (v5)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import shutil
import stat
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from contextlib import ExitStack, nullcontext, suppress
from functools import partial
from pathlib import Path
from typing import Any, Callable

from execution_contracts import (MANAGER_IDENTITY_FIELDS, TERMINAL_UNCERTAIN_STATUSES, ContractError, canonical,
                                 chartered_test_argv_supported,
                                 digest, envelope_digest, handback_supported, validate_manager_identity,
                                 expected_magentic_action_id, expected_manager_call_id,
                                 expected_replan_id, validate_action, validate_manager_call,
                                 validate_result, validate_receipt, validate_envelope)
from execution_ledger import ExecutionLedger, utc_now
from delivery_control import DeliveryControlError, delivery_authority_guard
from delivery_projection import lead_claim_active
import delivery_termination
import delivery_cancel
import process_identity
from manager_requests import render_manager_prompt, request_bytes, write_request_file
from delivery_recovery import (ATTEMPT_NOT_PAUSED, ATTEMPT_TERMINAL, CONTINUATION_EPOCHS_V5_ONLY, ENVELOPE_CHANGED, EVIDENCE_FILE_REQUIRED,
                               EXPECTED_GENERATION_REQUIRED, EXPECTED_GENERATION_V8_ONLY, LEAD_GENERATION_INACTIVE,
                               OWNER_GENERATION_STALE, V8_DISPOSITION_UNSUPPORTED, V8_EVIDENCE_FILE_REFUSED,
                               RecoveryRefused,
                               SIBLING_ATTEMPT_NOT_TERMINAL,
                               V6_INSPECTION_ONLY, V7_NOT_RECOVERABLE, WORKTREE_CONTAINS_PROJECT_FLOW, WORKTREE_DRIFT,
                               build_recovery_block, denied_reply,
                               rebuild_chartered_evidence_plan, recovery_eligibility, restore_position,
                               runtime_outcome)
from delivery_contracts import (DELIVERY_CHARTER_VERSION, DeliveryContractError, digest as delivery_digest,
                                project_envelope_limits, validate_delivery_charter, validate_shaper_contract)
from execution_gateway import _effective_specialist_for, _run_file, _write_snapshot, resolve_attempt
from fsutil import repo_root, write_atomic
from local_worker import call_local
from provider_availability import normalize_availability
from provider_selection import merge_selection_policy
from selection_authority import seal_selection_authority
from provider_availability import discover_ollama_models, AvailabilityError
from flowtoml import read_toml
from paths import SCAFFOLD_DIR, USER_OVERLAY_DIR
from delivery_selection import (authorize_and_dispatch as authorize_v9_and_dispatch,
                                compute_binding as compute_v9_binding,
                                make_action as make_v9_action,
                                _runtime_family_exclusions)
from ollama_edit_worker import (propose_edits as propose_ollama_edits,
                                source_bundle as ollama_source_bundle,
                                validate_and_apply as apply_ollama_edits)
from ollama_manager import call_ollama_manager
from runner_progress import parse_progress
from claude_worker import call_claude
from claude_edit_worker import MAX_TRACE_BYTES, _stream_result, call_claude_edit
from codex_worker import call_codex
from maf_supervisor import (MafChildError, MafProtocolError, MafTransportError, run_maf_delivery,
                            run_maf_v9_delivery)
from maf_runtime import require_ready
from orchestration import validate_orchestration
from runstate import handoff_to_review, status as run_status
from runner_limits import MAX_MANAGER_MESSAGES_BYTES, MAX_MANAGER_CALLS, MAX_ACTIONS
from verifier_contracts import (VERIFIED_HANDOFF_AUTHORITY, VERIFIER_CONTRACT_INSTRUCTION,
                                evaluate_candidate, provider_binding_mismatch,
                                verifier_instructions, verifier_provider_task)

APPROVED_PATHS = ("cli/codex_worker.py", "tests/test_codex_worker.py")
ROSTER_IDS = ("claude-implementer", "local-analyst", "local-verifier")
MAX_TASK_BYTES = 4096
MAX_CHARTERED_DIFF_BYTES = 1024 * 1024
# The missed-cancel bound for a wait that cannot watch the wakeup pipe.
CANCEL_POLL_SECONDS = 0.25


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ExpansionPaused(Exception):
    """A v8 proposal needs an engineer expansion decision; nothing was sent for it."""

    def __init__(self, request_id: str) -> None:
        super().__init__(f"expansion decision required: {request_id}")
        self.request_id = request_id


def _pending_expansion(decision: dict[str, Any]) -> str | None:
    expansion = decision.get("expansion")
    if not decision["allowed"] and isinstance(expansion, dict) and expansion.get("status") == "pending":
        return expansion["request_id"]
    return None


def _safe_job_path(path: Any) -> str:
    if (not isinstance(path, str) or not path or Path(path).is_absolute()
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or "\\" in path or ".git" in path.split("/")):
        raise ContractError("job path is not a safe relative path")
    return path


def _path_within_scopes(relative: str, scopes: list[str]) -> bool:
    """Treat charter paths as file-or-directory scopes, consistently."""
    path = Path(relative)
    if path.is_absolute() or any(part in {"", ".", "..", ".git"} for part in path.parts):
        return False
    return any(path == Path(scope) or path.is_relative_to(Path(scope)) for scope in scopes)


def _read_sealed_json(path: Path, name: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ContractError(f"sealed delivery {name} is unavailable")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"sealed delivery {name} is invalid") from exc
    if not isinstance(value, dict):
        raise ContractError(f"sealed delivery {name} is invalid")
    return value


def _sealed_delivery_authority(run_dir: Path, delivery: dict[str, Any]) -> dict[str, Any]:
    """Load every sealed ownership record and prove its cross-links.

    Runtime preparation must not trust a digest copied into mutable run state.
    It reads the immutable contract files, validates their own digests, then
    proves that the current active claim belongs to the sealed charter.
    """
    required = {"shaper_contract_digest", "charter_digest", "handoff_digest", "lead_claim_digest",
                "lead_claim_path", "delivery_artifact_dir", "owner_generation", "owner_status", "source_digests"}
    if not isinstance(delivery, dict) or not required.issubset(delivery):
        raise ContractError("chartered delivery requires sealed Flow ownership artifacts")
    if delivery["owner_status"] != "active" or type(delivery["owner_generation"]) is not int or delivery["owner_generation"] < 1:
        raise ContractError("sealed Flow delivery owner is not active")
    for field in ("shaper_contract_digest", "charter_digest", "handoff_digest", "lead_claim_digest"):
        if not isinstance(delivery[field], str) or len(delivery[field]) != 64:
            raise ContractError("sealed Flow delivery ownership is invalid")
    claim_rel = delivery["lead_claim_path"]
    if (not isinstance(claim_rel, str) or not claim_rel.startswith("delivery/")
            or any(part in {"", ".", ".."} for part in claim_rel.split("/"))):
        raise ContractError("sealed Flow lead claim path is invalid")
    artifact_rel = delivery["delivery_artifact_dir"]
    if (not isinstance(artifact_rel, str) or not artifact_rel.startswith("delivery/")
            or any(part in {"", ".", ".."} for part in artifact_rel.split("/"))):
        raise ContractError("sealed Flow delivery artifact path is invalid")
    delivery_dir = run_dir / artifact_rel
    shaper = _read_sealed_json(delivery_dir / "shaper-contract.json", "Shaper Contract")
    charter = _read_sealed_json(delivery_dir / "delivery-charter.json", "Delivery Charter")
    handoff = _read_sealed_json(delivery_dir / "handoff.json", "handoff")
    claim = _read_sealed_json(run_dir / claim_rel, "lead claim")
    try:
        validate_shaper_contract(shaper)
        validate_delivery_charter(charter)
    except DeliveryContractError as exc:
        raise ContractError("sealed Flow contract is invalid") from exc
    if shaper.get("digest") != delivery["shaper_contract_digest"] or charter.get("digest") != delivery["charter_digest"]:
        raise ContractError("sealed Flow contract digest differs from run authority")
    handoff_payload = dict(handoff)
    handoff_digest = handoff_payload.pop("digest", None)
    if handoff_digest != delivery_digest(handoff_payload) or handoff_digest != delivery["handoff_digest"]:
        raise ContractError("sealed Flow handoff digest differs from run authority")
    claim_payload = dict(claim)
    claim_digest = claim_payload.pop("digest", None)
    if claim_digest != delivery_digest(claim_payload) or claim_digest != delivery["lead_claim_digest"]:
        raise ContractError("sealed Flow lead claim digest differs from run authority")
    if (charter.get("shaper_contract", {}).get("digest") != shaper.get("digest")
            or handoff.get("shaper_contract_digest") != shaper.get("digest")
            or handoff.get("delivery_charter_digest") != charter.get("digest")
            or claim.get("charter_digest") != charter.get("digest")
            or claim.get("generation") != delivery["owner_generation"]
            or claim.get("status") != "active"
            or not isinstance(claim.get("owner"), str) or not claim["owner"].strip()):
        raise ContractError("sealed Flow ownership cross-link is invalid")
    if charter.get("approved_sources") != delivery["source_digests"] or handoff.get("source_digests") != delivery["source_digests"]:
        raise ContractError("sealed Flow source snapshot differs from delivery authority")
    return {"shaper": shaper, "charter": charter, "handoff": handoff, "claim": claim}


def _job_test(test: Any) -> dict[str, Any]:
    if not isinstance(test, dict) or set(test) != {"argv", "timeout_seconds"}:
        raise ContractError("targeted test specification is invalid")
    argv, timeout = test["argv"], test["timeout_seconds"]
    if (not isinstance(argv, list)
            or any(not isinstance(arg, str) or not arg or len(arg) > 256 or "\x00" in arg for arg in argv)
            or argv[0] not in {"python3", "python3.12", "/opt/homebrew/bin/python3.12"}
            or not chartered_test_argv_supported(argv)
            or type(timeout) is not int or not 1 <= timeout <= 3600):
        raise ContractError("targeted test argv or deadline is unsupported")
    return test


def _git(worktree: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(worktree), *args], capture_output=True,
                            text=True, timeout=15, check=False)
    if result.returncode:
        raise ContractError("isolated worktree Git check failed")
    return result.stdout.rstrip("\n")


def _worktree_baseline(worktree: Path, source_commit: str) -> dict[str, Any]:
    if worktree.is_symlink() or not worktree.is_dir() or _git(worktree, "rev-parse", "HEAD") != source_commit:
        raise ContractError("isolated worktree does not match pinned source commit")
    changes = _git(worktree, "status", "--porcelain", "--untracked-files=all").splitlines()
    if len(changes) != 1 or changes[0][:2] not in {" M", "M "} or changes[0][3:] != "tests/test_codex_worker.py":
        raise ContractError("isolated worktree requires only the approved failing regression")
    if not _git(worktree, "diff", "HEAD", "--", "tests/test_codex_worker.py"):
        raise ContractError("approved regression diff is absent")
    if _git(worktree, "diff", "--name-only", "HEAD", "--") != "tests/test_codex_worker.py":
        raise ContractError("worktree baseline includes changes outside the approved regression")
    return {"source_commit": source_commit,
            "files": {path: hashlib.sha256((worktree / path).read_bytes()).hexdigest() for path in APPROVED_PATHS},
            "regression_diff_sha256": hashlib.sha256(_git(worktree, "diff", "HEAD", "--", "tests/test_codex_worker.py").encode()).hexdigest()}


def prepare_delivery(work_id: str, worktree: Path, source_commit: str, *,
                     root: Path | None = None) -> tuple[dict[str, Any], str, Path, ExecutionLedger]:
    """Pin approved charter, effective roster, source, and baseline before any send."""
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    state = run_status(work_id, root=project_root)
    if state.get("state") != "implementing" or state.get("protocol_revision") != 2:
        raise ContractError("delivery requires an implementing revision-2 run")
    valid, _, findings = validate_orchestration(work_id, "dispatch", root=project_root)
    if not valid:
        raise ContractError("orchestration dispatch invalid: " + "; ".join(f.message for f in findings))
    manifest_path = run_dir / "orchestration.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    assignments = {a["id"]: a for a in manifest["assignments"] if a.get("lane") == "implement"}
    if set(assignments) != {"magentic-manager", *ROSTER_IDS}:
        raise ContractError("approved Delivery Lead roster is absent or expanded")
    manager = assignments["magentic-manager"]
    if manager.get("role") != "delivery-lead" or manager.get("execution", {}).get("provider") != "claude":
        raise ContractError("approved manager binding is invalid")
    roster = []
    for assignment_id in ROSTER_IDS:
        entry = assignments[assignment_id]
        role = "lead-developer" if assignment_id == "claude-implementer" else "test-engineer"
        provider = "claude" if assignment_id == "claude-implementer" else "ollama"
        execution = entry.get("execution", {})
        if entry.get("role") != role or execution.get("provider") != provider or not execution.get("model"):
            raise ContractError("approved specialist binding is invalid")
        instructions = _effective_specialist_for(role)
        roster.append({"assignment_id": assignment_id, "definition_digest": digest({"role": role, "instructions": instructions}),
                       "instance_id": assignment_id, "role": role, "provider": provider,
                       "model": execution["model"], "instructions": instructions})
    if assignments["claude-implementer"].get("write_scopes") != list(APPROVED_PATHS):
        raise ContractError("Claude edit scope differs from approved paths")
    charter_path = _run_file(project_root, run_dir, str((run_dir / "job-charter.md").relative_to(project_root)))
    task = charter_path.read_text()
    if not task.strip() or len(task.encode()) > MAX_TASK_BYTES:
        raise ContractError("delivery job charter is absent or oversized")
    artifacts = state.get("artifacts", {})
    requirements = _run_file(project_root, run_dir, artifacts.get("requirements", ""))
    acceptance = _run_file(project_root, run_dir, artifacts.get("acceptance_criteria", ""))
    requirements_bytes, acceptance_bytes = requirements.read_bytes(), acceptance.read_bytes()
    worktree = Path(worktree).resolve(strict=True)
    baseline = _worktree_baseline(worktree, source_commit)
    baseline["regression_test"] = _verify_failing_regression(worktree)
    attempt_id = uuid.uuid4().hex
    execution_dir = run_dir / "execution"
    execution_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(execution_dir, 0o700)
    attempt_dir = execution_dir / attempt_id
    attempt_dir.mkdir(mode=0o700)
    (attempt_dir / "checkpoints").mkdir(mode=0o700)
    for data, name in ((manifest_bytes, "manifest.snapshot.json"), (requirements_bytes, "requirements.snapshot.md"),
                       (acceptance_bytes, "acceptance.snapshot.md"), (task.encode(), "job-charter.snapshot.md")):
        _write_snapshot(attempt_dir / name, data)
    if any(path.read_bytes() != data for path, data in ((manifest_path, manifest_bytes),
              (requirements, requirements_bytes), (acceptance, acceptance_bytes), (charter_path, task.encode()))):
        raise ContractError("approved delivery sources changed during preparation")
    envelope = {"schema_version": 1, "execution_protocol_version": 5, "work_id": work_id, "attempt_id": attempt_id,
                "charter_digest": digest({"requirements": hashlib.sha256(requirements_bytes).hexdigest(),
                                          "acceptance": hashlib.sha256(acceptance_bytes).hexdigest()}),
                "charter_sources": {"requirements": {"path": str(requirements.relative_to(project_root)), "sha256": hashlib.sha256(requirements_bytes).hexdigest()},
                                    "acceptance": {"path": str(acceptance.relative_to(project_root)), "sha256": hashlib.sha256(acceptance_bytes).hexdigest()}},
                "run_protocol_revision": 2, "manifest_digest": hashlib.sha256(manifest_bytes).hexdigest(),
                "checkpoint_dir": str(attempt_dir / "checkpoints"), "source_commit": source_commit,
                "worktree": str(worktree), "allowed_paths": list(APPROVED_PATHS),
                "manager": {"provider": "claude", "model": manager["execution"]["model"]}, "roster": roster,
                "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2,
                           "max_manager_calls": 12, "max_manager_rounds": 6, "max_paid_worker_calls": 1}}
    envelope_digest(envelope)
    write_atomic(attempt_dir / "envelope.json", canonical(envelope) + "\n", mode=0o600)
    write_atomic(attempt_dir / "baseline.json", canonical(baseline) + "\n", mode=0o600)
    ledger = ExecutionLedger(execution_dir / "ledger.sqlite")
    ledger.create_attempt(envelope)
    return envelope, task, attempt_dir, ledger


def _refuse_project_flow_in_worktree(worktree: Path, project_root: Path) -> None:
    """Keep the run's ledger and attempt evidence out of a chartered worker's reach.

    A Codex producer can write anywhere in its worktree, so a worktree that is,
    contains, or sits inside the project ``.flow`` could forge Flow's evidence.
    """
    # Compare files, not spellings: a case-insensitive volume, a firmlink, or
    # a bind mount can give one directory two different paths.
    def identities(path: Path) -> set[tuple[int, int]]:
        found = set()
        for candidate in (path, *path.parents):
            try:
                info = candidate.stat()
            except OSError:
                continue
            found.add((info.st_dev, info.st_ino))
        return found

    flow_dir = (project_root / ".flow").resolve()
    resolved = Path(worktree).resolve()
    try:
        flow_info, tree_info = flow_dir.stat(), resolved.stat()
    except OSError:
        flow_info = tree_info = None
    if (resolved == flow_dir or resolved in flow_dir.parents or flow_dir in resolved.parents
            or (flow_info is not None and ((flow_info.st_dev, flow_info.st_ino) in identities(resolved)
                                           or (tree_info.st_dev, tree_info.st_ino) in identities(flow_dir)))):
        raise RecoveryRefused(WORKTREE_CONTAINS_PROJECT_FLOW, str(resolved))


def prepare_chartered_delivery(work_id: str, worktree: Path, source_commit: str, *,
                               root: Path | None = None) -> tuple[dict[str, Any], str, Path, ExecutionLedger]:
    """Resolve an approved generic charter into a pinned v7 attempt before any send."""
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    state = run_status(work_id, root=project_root)
    if state.get("state") != "implementing" or state.get("protocol_revision") != 2:
        raise ContractError("chartered delivery requires an implementing revision-2 run")
    delivery = state.get("delivery")
    authority = _sealed_delivery_authority(run_dir, delivery)
    valid, _, findings = validate_orchestration(work_id, "dispatch", root=project_root)
    if not valid:
        raise ContractError("orchestration dispatch invalid: " + "; ".join(f.message for f in findings))
    artifacts = state.get("artifacts", {})
    charter_rel = artifacts.get("job_charter")
    manifest_path = _run_file(project_root, run_dir, artifacts.get("orchestration_manifest", ""))
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    manager_matches = [a for a in manifest.get("assignments", []) if a.get("lane") == "implement" and a.get("id") == "magentic-manager"]
    expected_charter = f".flow/runs/{work_id}/job-charter.json"
    manifest_linked = len(manager_matches) == 1 and expected_charter in manager_matches[0].get("input_evidence", [])
    if (charter_rel is not None and charter_rel != expected_charter) or (charter_rel is None and not manifest_linked):
        raise ContractError("approved job charter artifact is absent")
    charter_path = _run_file(project_root, run_dir, expected_charter)
    requirements = _run_file(project_root, run_dir, artifacts.get("requirements", ""))
    acceptance = _run_file(project_root, run_dir, artifacts.get("acceptance_criteria", ""))
    source_paths = (charter_path, manifest_path, requirements, acceptance)
    source_bytes = {path: (manifest_bytes if path == manifest_path else path.read_bytes()) for path in source_paths}
    charter = json.loads(source_bytes[charter_path])
    required_charter_fields = {"task", "read_paths", "write_paths", "test", "producer_instance_ids", "verifier_instance_ids", "baseline"}
    if (not isinstance(charter, dict) or not required_charter_fields.issubset(charter)
            or set(charter) - required_charter_fields != {"evidence_collector_instance_ids"} and set(charter) != required_charter_fields):
        raise ContractError("job charter fields are invalid")
    task = charter["task"]
    if not isinstance(task, str) or not task.strip() or len(task.encode()) > MAX_TASK_BYTES:
        raise ContractError("job task is empty or oversized")
    for field in ("read_paths", "write_paths", "producer_instance_ids", "verifier_instance_ids"):
        if not isinstance(charter[field], list) or not charter[field] or len(charter[field]) != len(set(charter[field])):
            raise ContractError(f"job {field} is invalid")
    for field in ("read_paths", "write_paths"):
        for path in charter[field]:
            _safe_job_path(path)
    _job_test(charter["test"])
    assignments = [a for a in manifest.get("assignments", []) if a.get("lane") == "implement"]
    ids = [a.get("id") for a in assignments]
    if len(ids) != len(set(ids)) or ids.count("magentic-manager") != 1:
        raise ContractError("manager or specialist instance is duplicated or absent")
    manager = next(a for a in assignments if a["id"] == "magentic-manager")
    if manager.get("role") != "delivery-lead" or manager.get("execution", {}).get("provider") not in {"claude", "codex"} or not manager["execution"].get("model"):
        raise ContractError("approved manager binding is unsupported")
    specialists = [a for a in assignments if a["id"] != "magentic-manager"]
    if not specialists or len(specialists) > 6:
        raise ContractError("approved roster is absent or expanded")
    roster = []
    for entry in specialists:
        execution = entry.get("execution", {})
        provider = execution.get("provider")
        model = execution.get("model")
        read_only = entry.get("read_only") is True
        if provider not in {"claude", "codex", "ollama"} or not isinstance(model, str) or not model.strip():
            raise ContractError("specialist provider or model is unsupported")
        if (provider == "ollama" and not read_only) or (provider == "claude" and read_only):
            raise ContractError("specialist provider and permissions disagree")
        if not read_only and entry.get("write_scopes") != charter["write_paths"]:
            raise ContractError("editing assignment scope differs from charter")
        if read_only and entry.get("write_scopes"):
            raise ContractError("read-only assignment has write scope")
        role = entry.get("role")
        instructions = _effective_specialist_for(role)
        roster.append({"assignment_id": entry["id"], "definition_digest": digest({"role": role, "instructions": instructions}),
                       "instance_id": entry["id"], "role": role, "provider": provider,
                       "model": model, "instructions": instructions,
                       "capabilities": ["read"] if read_only else ["read", "edit"]})
    by_id = {item["instance_id"]: item for item in roster}
    producers = charter["producer_instance_ids"]
    evidence_collectors = charter.get("evidence_collector_instance_ids", [])
    verifiers = charter["verifier_instance_ids"]
    if any(item not in by_id or "edit" not in by_id[item]["capabilities"] for item in producers):
        raise ContractError("producer is not an approved editor")
    if any(item not in by_id or by_id[item]["capabilities"] != ["read"] for item in verifiers) or set(producers) & set(verifiers):
        raise ContractError("verifier is not an independent read-only specialist")
    if (len(evidence_collectors) != len(set(evidence_collectors))
            or any(item not in by_id or by_id[item]["capabilities"] != ["read"] for item in evidence_collectors)
            or set(evidence_collectors) & (set(producers) | set(verifiers))):
        raise ContractError("evidence collector is not a distinct read-only specialist")
    verification = manifest.get("verification") or {}
    designated_verifier = verification.get("verifier_assignment")
    evidence_collector = verification.get("evidence_collector_assignment")
    if (designated_verifier not in verifiers or evidence_collector in verifiers
            or evidence_collector == designated_verifier):
        raise ContractError("job verifier set conflicts with independent orchestration roles")
    if evidence_collectors and evidence_collector not in evidence_collectors:
        raise ContractError("job evidence collector differs from orchestration role")
    # The execution projection may narrow the canonical Charter, never widen
    # it. Provider, role cardinality, limits, and producer/verifier separation
    # are proven before an attempt or grant exists.
    canonical_charter = authority["charter"]
    eligible_roles = canonical_charter["eligible_specialists"]
    role_counts: dict[str, int] = {}
    for item in roster:
        role_counts[item["role"]] = role_counts.get(item["role"], 0) + 1
        sealed_role = eligible_roles.get(item["role"], {})
        role_limit = sealed_role.get("maximum_instances")
        if (item["provider"] not in canonical_charter["provider_capabilities"]
                or item["definition_digest"] != sealed_role.get("definition_digest")
                or not set(item["capabilities"]).issubset(set(sealed_role.get("runtime_capabilities", [])))
                or not isinstance(role_limit, int) or role_counts[item["role"]] > role_limit):
            raise ContractError("runtime roster expands the sealed Delivery Charter")
    canonical_limits = canonical_charter["limits"]
    if "max_verifier_calls" not in canonical_limits:
        # Protocol v8 enforces the verifier allowance the Charter sealed; a
        # legacy Charter never sealed one, so Flow will not invent a default.
        raise ContractError("protocol v8 requires a Delivery Charter that seals max_verifier_calls")
    if canonical_charter.get("charter_version") != DELIVERY_CHARTER_VERSION:
        # ADR 0020: the lineage token budget is sealed, never defaulted.
        raise ContractError("protocol v8 requires a Delivery Charter that seals a token budget")
    if len(specialists) > canonical_limits.get("delegations", 0):
        raise ContractError("runtime roster expands the sealed Delivery Charter")
    if (canonical_limits.get("paths") != ["charter-scoped"]
            or not {"read", "edit", "test"}.issubset(set(canonical_limits.get("tools", [])))
            or not {"diff", "test", "receipt"}.issubset(set(canonical_limits.get("outputs", [])))):
        raise ContractError("runtime scope is not permitted by the sealed Delivery Charter")
    verifier_rules = canonical_charter.get("producer_verifier_rules")
    if (not isinstance(verifier_rules, dict) or not verifier_rules.get("distinct_identities")
            or not verifier_rules.get("verifier_read_only")):
        raise ContractError("runtime verifier rules expand the sealed Delivery Charter")
    raw_worktree = Path(worktree)
    if raw_worktree.is_symlink():
        raise ContractError("isolated worktree path is a symlink")
    worktree = raw_worktree.resolve(strict=True)
    _refuse_project_flow_in_worktree(worktree, project_root)
    if _git(worktree, "rev-parse", "HEAD") != source_commit or _git(worktree, "rev-parse", "--show-toplevel") != str(worktree):
        raise ContractError("isolated worktree does not match pinned source commit")
    for relative in set(charter["read_paths"] + charter["write_paths"]):
        current = worktree
        for part in relative.split("/"):
            current /= part
            if current.is_symlink():
                raise ContractError("job scope contains a symlink")
        if worktree not in current.resolve().parents:
            raise ContractError("job scope escapes isolated worktree")
    lines = _git(worktree, "status", "--porcelain", "--untracked-files=all").splitlines()
    baseline = charter["baseline"]
    if not isinstance(baseline, dict) or set(baseline) != {"kind", "diff_sha256"}:
        raise ContractError("job baseline is invalid")
    diff = _git(worktree, "diff", "HEAD", "--").encode()
    if baseline["kind"] == "clean":
        if lines or diff or baseline["diff_sha256"] != hashlib.sha256(b"").hexdigest():
            raise ContractError("isolated worktree baseline is not clean")
    elif baseline["kind"] == "declared_regression":
        if (not diff or baseline["diff_sha256"] != hashlib.sha256(diff).hexdigest()
                or any(not _path_within_scopes(line[3:], charter["write_paths"]) for line in lines)):
            raise ContractError("declared regression differs from pinned baseline")
    else:
        raise ContractError("job baseline kind is unsupported")
    job_baseline = {key: baseline[key] for key in ("kind", "diff_sha256")}
    baseline_files = {}
    for line in lines:
        relative = line[3:]
        path = worktree / relative
        if path.is_file() and _path_within_scopes(relative, charter["write_paths"]):
            baseline_files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    baseline = {"regression_diff_sha256": baseline["diff_sha256"], "source_commit": source_commit,
                "files": baseline_files}
    # This is the pre-attempt fence. All authority and worktree proof above is
    # read-only. No execution directory, ledger row, receipt, process, or
    # provider callback exists until the optional runtime is healthy.
    runtime_identity = require_ready()
    execution_dir = run_dir / "execution"
    # A successor lists every earlier v8 attempt so its spend shares the
    # charter caps; the ledger re-checks the list inside create_attempt.
    predecessors: list[dict[str, Any]] = []
    if (execution_dir / "ledger.sqlite").is_file():
        predecessors, started = ExecutionLedger(execution_dir / "ledger.sqlite", read_only=True).v8_lineage(work_id)
        if started:
            raise RecoveryRefused(SIBLING_ATTEMPT_NOT_TERMINAL, "an earlier attempt of this delivery is still started")
    attempt_id = uuid.uuid4().hex
    execution_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(execution_dir, 0o700)
    attempt_dir = execution_dir / attempt_id
    attempt_dir.mkdir(mode=0o700)
    (attempt_dir / "checkpoints").mkdir(mode=0o700)
    for path, name in ((charter_path, "job-charter.snapshot.json"), (manifest_path, "manifest.snapshot.json"),
                       (requirements, "requirements.snapshot.md"), (acceptance, "acceptance.snapshot.md")):
        _write_snapshot(attempt_dir / name, source_bytes[path])
    if any(path.read_bytes() != data for path, data in source_bytes.items()) or _git(worktree, "rev-parse", "HEAD") != source_commit:
        raise ContractError("approved delivery source changed during preparation")
    sources = {name: {"path": str(path.relative_to(project_root)), "sha256": hashlib.sha256(source_bytes[path]).hexdigest()}
               for name, path in (("requirements", requirements), ("acceptance", acceptance))}
    job_contract = {"task": task, "baseline": job_baseline,
                    "read_paths": charter["read_paths"], "write_paths": charter["write_paths"],
                    "test": charter["test"], "producer_instance_ids": producers,
                    "evidence_collector_instance_ids": evidence_collectors,
                    "verifier_instance_ids": verifiers}
    # One projection, shared with verify-receipt (ADR 0020).
    limits, headroom = project_envelope_limits(canonical_limits)
    envelope = {"schema_version": 1, "execution_protocol_version": 8, "work_id": work_id, "attempt_id": attempt_id,
                "charter_digest": digest({"requirements": sources["requirements"]["sha256"], "acceptance": sources["acceptance"]["sha256"]}),
                "charter_sources": sources, "run_protocol_revision": 2,
                "manifest_digest": hashlib.sha256(source_bytes[manifest_path]).hexdigest(),
                "checkpoint_dir": str(attempt_dir / "checkpoints"), "source_commit": source_commit,
                "worktree": str(worktree), "allowed_paths": charter["write_paths"],
                "manager": {"provider": manager["execution"]["provider"], "model": manager["execution"]["model"]},
                "roster": roster, "job_contract": job_contract,
                # These links project Flow's canonical authority into the
                # runtime boundary. The child receives digests only.
                "shaper_contract_digest": delivery["shaper_contract_digest"],
                "delivery_charter_digest": delivery["charter_digest"],
                "handoff_digest": delivery["handoff_digest"],
                "delivery_lead_claim_digest": delivery["lead_claim_digest"],
                "delivery_lead_claim": {"lead_id": authority["claim"]["owner"], "generation": delivery["owner_generation"]},
                "maf_runtime": runtime_identity,
                "limits": limits}
    if predecessors:
        # Added only when non-empty, so a first attempt stays byte-identical.
        envelope["predecessors"] = predecessors
    if headroom:
        # Projected from the sealed Charter only; omitted when none is sealed.
        envelope["expansion_headroom"] = headroom
    envelope_digest(envelope)
    write_atomic(attempt_dir / "envelope.json", canonical(envelope) + "\n", mode=0o600)
    write_atomic(attempt_dir / "baseline.json", canonical(baseline) + "\n", mode=0o600)
    ledger = ExecutionLedger(execution_dir / "ledger.sqlite")
    # Under run_lock, so a lead change cannot seal the lineage and bump the
    # claim between reading it and creating this attempt; a stale claim is
    # refused here instead of leaving a started sibling that blocks successors.
    with delivery_authority_guard(run_dir, envelope):
        ledger.create_attempt(envelope)
    return envelope, task, attempt_dir, ledger


def _normalized_manager_request(envelope: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    messages = message.get("messages")
    if (not isinstance(messages, list) or not messages
            or len(canonical(messages).encode()) > MAX_MANAGER_MESSAGES_BYTES):
        raise ContractError("Magentic manager messages are invalid")
    request = {key: message.get(key) for key in ("schema_version", "call_id", "attempt_id", "envelope_digest",
                                                "sequence", "phase", "manager_round", "prompt_digest")}
    for key in ("replan_sequence", "replan_id"):
        if key in message:
            request[key] = message[key]
    if request["prompt_digest"] != digest(messages):
        raise ContractError("Magentic manager prompt digest differs from messages")
    validate_manager_call(envelope, request)
    return request


def _normalized_action(envelope: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    task = message.get("task")
    if not isinstance(task, str) or not task.strip() or len(task.encode()) > MAX_TASK_BYTES:
        raise ContractError("Magentic specialist task is invalid")
    keys = ("schema_version", "kind", "attempt_id", "envelope_digest", "sequence", "assignment_id",
            "definition_digest", "instance_id", "role", "provider", "model", "manager_turn", "task",
            "rationale", "parent_action_id", "checkpoint_id")
    action = {key: message.get(key) for key in keys}
    if envelope["execution_protocol_version"] in {7, 8}:
        action["provider_choice"] = message.get("provider_choice")
    action["task_digest"] = hashlib.sha256(task.encode()).hexdigest()
    expected_id = expected_magentic_action_id(action)
    if message.get("action_id") != expected_id:
        raise ContractError("Magentic specialist action ID differs from selected task")
    action["action_id"] = expected_id
    validate_action(envelope, action)
    return action


def _verify_edit(worktree: Path, baseline: dict[str, Any], attempt_dir: Path) -> dict[str, Any]:
    changed = _git(worktree, "diff", "--name-only", "HEAD", "--").splitlines()
    if not changed or any(path not in APPROVED_PATHS for path in changed):
        raise ContractError("Claude changed files outside the approved repair scope")
    if _git(worktree, "status", "--porcelain", "--untracked-files=all") and any(
            line[:2] not in {" M", "M "} or line[3:] not in APPROVED_PATHS
            for line in _git(worktree, "status", "--porcelain", "--untracked-files=all").splitlines()):
        raise ContractError("Claude created or changed an unapproved worktree entry")
    if hashlib.sha256((worktree / "cli/codex_worker.py").read_bytes()).hexdigest() == baseline["files"]["cli/codex_worker.py"]:
        raise ContractError("Claude did not change the approved implementation target")
    diff = _git(worktree, "diff", "HEAD", "--", *APPROVED_PATHS).encode()
    if not diff or len(diff) > 16384:
        raise ContractError("Claude repair diff is empty or oversized")
    diff_path = attempt_dir / "repair.diff"
    if diff_path.exists():
        if diff_path.is_symlink() or diff_path.read_bytes() != diff:
            raise ContractError("recorded Claude repair diff changed")
    else:
        _write_snapshot(diff_path, diff)
    return {"changed_files": changed, "diff_sha256": hashlib.sha256(diff).hexdigest(),
            "diff_path": str(attempt_dir / "repair.diff"),
            "files": {path: hashlib.sha256((worktree / path).read_bytes()).hexdigest() for path in APPROVED_PATHS}}


def _run_targeted_test(worktree: Path) -> dict[str, Any]:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_codex_worker.py"]
    try:
        completed = subprocess.run(command, cwd=worktree, capture_output=True, text=True, timeout=90, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ContractError("targeted repair test timed out") from exc
    output = (completed.stdout + completed.stderr)[-8192:]
    if completed.returncode:
        raise ContractError("targeted repair test failed: " + output[-512:])
    return {"command": command, "status": "passed", "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


def _verify_failing_regression(worktree: Path) -> dict[str, Any]:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_codex_worker.py"]
    try:
        completed = subprocess.run(command, cwd=worktree, capture_output=True, text=True, timeout=90, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ContractError("baseline regression test timed out") from exc
    output = (completed.stdout + completed.stderr)[-8192:]
    if completed.returncode == 0 or "FAIL" not in output and "ERROR" not in output:
        raise ContractError("baseline regression is not a reproducible failing test")
    return {"command": command, "status": "failed_as_expected", "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "output_tail": output[-1024:]}


def execute_delivery(work_id: str, worktree: Path, source_commit: str, *, root: Path | None = None,
                     manager_adapter: Callable[..., dict[str, Any]] | None = None,
                     worker_adapter: Callable[..., dict[str, Any]] | None = None,
                     supervisor: Callable[..., dict[str, Any]] | None = None,
                     test_runner: Callable[[Path], dict[str, Any]] | None = None,
                     python_path: str | None = None) -> dict[str, Any]:
    """Authorize each manager and specialist call, then seal a linked receipt."""
    envelope, task, attempt_dir, ledger = prepare_delivery(work_id, worktree, source_commit, root=root)
    return _execute_prepared_delivery(envelope, task, attempt_dir, ledger,
                                      manager_adapter=manager_adapter, worker_adapter=worker_adapter,
                                      supervisor=supervisor, test_runner=test_runner, python_path=python_path)


def execute_chartered_delivery(work_id: str, worktree: Path, source_commit: str, *, root: Path | None = None,
                               manager_adapter: Callable[..., dict[str, Any]] | None = None,
                               worker_adapter: Callable[..., dict[str, Any]] | None = None,
                               supervisor: Callable[..., dict[str, Any]] | None = None,
                               seal_hook: Callable[[str], None] | None = None) -> dict[str, Any]:
    envelope, task, attempt_dir, ledger = prepare_chartered_delivery(work_id, worktree, source_commit, root=root)
    result = _execute_prepared_delivery(envelope, task, attempt_dir, ledger,
                                        manager_adapter=manager_adapter, worker_adapter=worker_adapter,
                                        supervisor=supervisor, test_runner=None, python_path=None,
                                        generation=envelope["delivery_lead_claim"]["generation"],
                                        seal_hook=seal_hook)
    if result.get("status") == "completed":
        project_root = (root or repo_root()).resolve()
        state = run_status(work_id, root=project_root)
        authority = _sealed_delivery_authority(project_root / ".flow" / "runs" / work_id,
                                               state.get("delivery", {}))
        if "handoff_to_review" in authority["charter"].get("allowed_lifecycle_operations", []):
            ok, payload, errors = handoff_to_review(
                work_id,
                result["attempt_id"],
                envelope["delivery_lead_claim"]["generation"],
                root=project_root,
            )
            if not ok:
                return {**result, "status": "handoff_failed", "reason": "; ".join(errors),
                        "review_handoff": {"status": "failed", "errors": errors}}
            result = {**result, "review_handoff": {"status": "completed", "state": payload["state"]}}
    return result


def recover_runtime_startup(work_id: str, attempt_id: str, worktree: Path, source_commit: str, *,
                            root: Path | None = None) -> dict[str, Any]:
    """Create a normal linked successor for one sealed zero-send MAF startup failure.

    This never reopens the predecessor.  The normal chartered prepare path
    rechecks authority, worktree and the now-healthy MAF runtime before it
    creates the successor attempt.
    """
    project_root = (root or repo_root()).resolve()
    ledger_path = project_root / ".flow" / "runs" / work_id / "execution" / "ledger.sqlite"
    if not ledger_path.is_file() or ledger_path.is_symlink():
        raise ContractError("runtime-startup predecessor is absent")
    snapshot = ExecutionLedger(ledger_path, read_only=True).snapshot(attempt_id)
    if snapshot.get("work_id") != work_id or snapshot.get("execution_protocol_version") != 8:
        raise ContractError("runtime-startup predecessor is incompatible")
    if snapshot.get("status") != "failed":
        raise ContractError("runtime-startup predecessor is not a terminal failure")
    if snapshot.get("failure_class") != "maf_runtime_startup":
        raise ContractError("terminal failure is not a MAF runtime-startup failure")
    sent = {"started", "completed", "failed", "unknown"}
    if any(item.get("status") in sent for item in snapshot.get("actions", [])) or any(
            item.get("status") in sent for item in snapshot.get("manager_calls", [])):
        raise ContractError("runtime-startup predecessor has observed or uncertain sends")
    receipt_path = Path(str(snapshot.get("receipt_path") or ""))
    expected_receipt = project_root / ".flow" / "runs" / work_id / "execution" / attempt_id / "receipt.json"
    if (receipt_path.resolve(strict=False) != expected_receipt.resolve(strict=False) or not receipt_path.is_file() or receipt_path.is_symlink()
            or not snapshot.get("sealed_receipt_sha256")):
        raise ContractError("runtime-startup predecessor receipt is not sealed")
    receipt_bytes = receipt_path.read_bytes()
    if hashlib.sha256(receipt_bytes).hexdigest() != snapshot["sealed_receipt_sha256"]:
        raise ContractError("runtime-startup predecessor receipt digest differs from ledger")
    try:
        receipt = json.loads(receipt_bytes)
    except (TypeError, ValueError) as exc:
        raise ContractError("runtime-startup predecessor receipt is invalid") from exc
    if (not isinstance(receipt, dict) or receipt.get("attempt_id") != attempt_id
            or receipt.get("envelope_digest") != envelope_digest(snapshot["envelope"])
            or receipt.get("status") != "failed" or receipt.get("reason") != snapshot.get("reason")
            or receipt.get("failure_class") != snapshot.get("failure_class")):
        raise ContractError("runtime-startup predecessor receipt identity differs from ledger")
    # Claim inside the ledger before preparing a new attempt: concurrent
    # recovery commands cannot both turn one sealed failure into successors.
    writable = ExecutionLedger(ledger_path)
    prior_successor = writable.reconcile_runtime_startup_successor(attempt_id)
    if prior_successor is not None:
        return {"attempt_id": prior_successor, "status": "reconciled", "predecessor_attempt_id": attempt_id}
    writable.claim_runtime_startup_successor(attempt_id)
    try:
        result = execute_chartered_delivery(work_id, worktree, source_commit, root=project_root)
    except Exception:
        writable.release_runtime_startup_successor(attempt_id)
        raise
    writable.bind_runtime_startup_successor(attempt_id, result["attempt_id"])
    return result


def _verify_chartered_edit(worktree: Path, baseline: dict[str, Any], attempt_dir: Path,
                           job: dict[str, Any], *, record: bool = True) -> dict[str, Any]:
    if _git(worktree, "rev-parse", "HEAD") != baseline["source_commit"]:
        raise ContractError("editor changed the pinned source commit")
    allowed = tuple(Path(path) for path in job["write_paths"])
    status = _git(worktree, "status", "--porcelain", "--untracked-files=all").splitlines()
    # Interpreter caches are execution residue, not source edits or verifier
    # evidence. Ignore them only while untracked; a tracked cache remains a
    # normal governed file and cannot evade scope or tamper checks.
    status = [line for line in status if not (
        line[:2] == "??" and (
            "__pycache__" in Path(line[3:]).parts or Path(line[3:]).suffix == ".pyc"
        )
    )]
    changed = [line[3:] for line in status]
    untracked = {path for line, path in zip(status, changed) if line[:2] == "??"}
    if not changed:
        raise ContractError("editor made no edit to the worktree")
    def in_scope(relative: str) -> bool:
        path = Path(relative)
        if path.is_absolute() or any(part in {"", ".", "..", ".git"} for part in path.parts):
            return False
        target = worktree / path
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(worktree.resolve()):
            return False
        return any(path == scope or path.is_relative_to(scope) for scope in allowed)
    permitted_statuses = {" M", "M ", "MM", "A ", "AM", "??"}
    if any(line[:2] not in permitted_statuses or not in_scope(path) for line, path in zip(status, changed)):
        raise ContractError("editor changed files outside the approved job scope")
    edited = [path for path in changed if ((worktree / path).is_file()
              and hashlib.sha256((worktree / path).read_bytes()).hexdigest() != baseline["files"].get(path))]
    if not edited:
        raise ContractError("editor made no edit: the allowed paths still match the pinned baseline")
    # The index is the declared-regression fence. Compare the producer's
    # worktree edit to that fence, not to HEAD, or verifier evidence contains
    # the pre-existing regression again and can exceed the bounded prompt.
    diff = _git(worktree, "diff", "--", *job["write_paths"]).encode()
    for path in edited:
        if path in untracked:
            diff += ("\nNEW FILE " + path + "\n").encode() + (worktree / path).read_bytes()
    if not diff:
        raise ContractError("chartered edit diff is empty")
    if len(diff) > MAX_CHARTERED_DIFF_BYTES:
        raise ContractError(
            f"chartered edit diff is {len(diff)} bytes; limit is {MAX_CHARTERED_DIFF_BYTES} bytes"
        )
    diff_path = attempt_dir / "repair.diff"
    if diff_path.exists():
        if diff_path.is_symlink() or diff_path.read_bytes() != diff:
            raise ContractError("recorded chartered diff changed")
    elif record:
        _write_snapshot(diff_path, diff)
    return {"changed_files": edited, "diff_sha256": hashlib.sha256(diff).hexdigest(),
            "diff_path": str(diff_path),
            "files": {path: hashlib.sha256((worktree / path).read_bytes()).hexdigest() for path in edited}}


def _run_chartered_test(worktree: Path, job: dict[str, Any], *,
                        on_process_group: Callable[[int, str], None] | None = None) -> dict[str, Any]:
    """Run the charter's targeted test in its own process group, killed whole on timeout."""
    test = _job_test(job["test"])
    process = subprocess.Popen(test["argv"], cwd=worktree, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, start_new_session=True)
    try:
        if on_process_group is not None:
            on_process_group(process.pid, "test")
        try:
            deadline = time.monotonic() + test["timeout_seconds"]
            with delivery_cancel.interruptible():  # test timeouts reach 3600 s
                # communicate() cannot watch the cancel wakeup pipe, so wait in
                # short slices and recheck between them: a SIGTERM that lands
                # just before a slice's select blocks breaks the wait when the
                # slice ends.
                while True:
                    try:
                        stdout, stderr = process.communicate(
                            timeout=max(0.0, min(CANCEL_POLL_SECONDS, deadline - time.monotonic())))
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            raise
                        delivery_cancel.wake()
        except subprocess.TimeoutExpired as exc:
            raise ContractError("targeted chartered test timed out") from exc
    finally:
        if process.poll() is None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            # An escaped grandchild could hold the pipes open; never wait on it forever.
            with suppress(subprocess.TimeoutExpired):
                process.communicate(timeout=10)
    output = (stdout + stderr)[-8192:]
    if process.returncode:
        raise ContractError("targeted chartered test failed: " + output[-512:])
    return {"command": test["argv"], "status": "passed",
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "output_excerpt": output}


def _peek_snapshot(ledger_path: Path, attempt_id: str) -> dict[str, Any] | None:
    """Read an attempt without opening the ledger for writing (which would run DDL)."""
    if not ledger_path.is_file() or ledger_path.is_symlink():
        return None
    try:
        return ExecutionLedger(ledger_path, read_only=True).snapshot(attempt_id)
    except (ContractError, sqlite3.Error):
        return None


def _recovery_gates(work_id: str, attempt_id: str, run_dir: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Decide on a read-only snapshot whether recovery may claim the attempt.

    Returns the snapshot and either the eligibility (recoverable) or None when
    a completed recovery should be reported instead. Refuses otherwise.
    """
    attempt_dir = run_dir / "execution" / attempt_id
    snapshot = _peek_snapshot(run_dir / "execution" / "ledger.sqlite", attempt_id)
    if snapshot is None or not attempt_dir.is_dir() or attempt_dir.is_symlink():
        raise ContractError("chartered attempt is absent")
    protocol = snapshot["execution_protocol_version"]
    if protocol == 6:
        raise RecoveryRefused(V6_INSPECTION_ONLY)
    if protocol == 7:
        raise RecoveryRefused(V7_NOT_RECOVERABLE)
    envelope = snapshot["envelope"]
    envelope_path = attempt_dir / "envelope.json"
    if (envelope["work_id"] != work_id or not envelope_path.is_file() or envelope_path.is_symlink()
            or json.loads(envelope_path.read_text()) != envelope):
        raise RecoveryRefused(ENVELOPE_CHANGED)
    if snapshot["status"] != "started":
        # A cancelled or abandoned attempt is never replayed, even after a
        # recovery: a person stopped it and its receipt is final (ADR 0019).
        if snapshot.get("recoveries") and snapshot["status"] not in TERMINAL_UNCERTAIN_STATUSES:
            return snapshot, None
        raise RecoveryRefused(ATTEMPT_TERMINAL)
    try:
        delivery = json.loads((run_dir / "run.json").read_text()).get("delivery")
    except (OSError, json.JSONDecodeError):
        delivery = None
    eligibility = recovery_eligibility(envelope, snapshot, lead_active=lead_claim_active(delivery, envelope))
    if not eligibility["recoverable"]:
        blockers = ", ".join(f"{item['kind']} {item['id']} {item['status']}" for item in eligibility["blockers"])
        raise RecoveryRefused(eligibility["reason"],
                              f"{blockers}; see flow run inspect-delivery {work_id} --attempt-id {attempt_id}")
    return snapshot, eligibility


def _resume_chartered(work_id: str, attempt_id: str, *, root: Path,
                      manager_adapter: Callable[..., dict[str, Any]] | None = None,
                      worker_adapter: Callable[..., dict[str, Any]] | None = None,
                      supervisor: Callable[..., dict[str, Any]] | None = None,
                      test_runner: Callable[[Path], dict[str, Any]] | None = None,
                      python_path: str | None = None, actor: str = "flow-chartered-resume",
                      seal_hook: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Recover a v6-v8 chartered attempt; only v8 is recoverable (ADR 0016).

    Every gate before the claim reads the ledger read-only, so a refusal
    leaves the ledger and attempt files unchanged (a recovery lock file may
    be created beside the ledger). The gates run only under the recovery
    lock: a live run holds it, so it refuses as ``attempt_running`` whatever
    its rows look like mid-send, and no live run can advance the attempt
    between the decision and the claim that acts on it.
    """
    run_dir = root / ".flow" / "runs" / work_id
    attempt_dir = run_dir / "execution" / attempt_id
    ledger_path = run_dir / "execution" / "ledger.sqlite"
    if not ledger_path.is_file() or ledger_path.is_symlink():
        raise ContractError("chartered attempt is absent")
    with ExecutionLedger(ledger_path, read_only=True).recovery_lock(attempt_id, holder="recovery"):
        snapshot, eligibility = _recovery_gates(work_id, attempt_id, run_dir)
        valid, _, findings = validate_orchestration(work_id, "dispatch", root=root)
        if not valid:
            raise ContractError("orchestration dispatch invalid: " + "; ".join(f.message for f in findings))
        if eligibility is None:
            # A completed recovery is reported, never repeated.
            return {"attempt_id": attempt_id, "status": snapshot["status"], "reason": snapshot["reason"],
                    "receipt_path": snapshot["receipt_path"], "replayed": True}
        envelope = snapshot["envelope"]
        mode = eligibility["mode"]
        link = eligibility["checkpoint"]
        expansion = eligibility.get("expansion")
        if "expansion_failure" in eligibility:
            outcome = {"failure": eligibility["expansion_failure"]}
        else:
            outcome = runtime_outcome(snapshot) if mode == "seal" else None
        recorded_failure = bool(outcome and outcome["failure"])
        if not recorded_failure:
            # Drift refuses before the claim, so it fences and releases nothing.
            _check_chartered_evidence(envelope, snapshot, attempt_dir)
        quarantine = _unbound_checkpoints(envelope, snapshot)
        ledger = ExecutionLedger(ledger_path)
        authority_guard = partial(delivery_authority_guard, run_dir, envelope)
        # Reconcile first: the claim fences and releases before any
        # checkpoint is read or any grant is issued.
        with authority_guard():
            claim = ledger.claim_chartered_recovery(
                attempt_id, expected_generation=snapshot["owner_generation"],
                expected_event_seq=snapshot["events"][-1]["seq"],
                lead_generation=envelope["delivery_lead_claim"]["generation"], actor=actor, mode=mode,
                checkpoint=({key: link[key] for key in ("pending_id", "checkpoint_id", "file_sha256")} if link else None),
                quarantined=quarantine, expansion_request_id=expansion["request_id"] if expansion else None)
        generation = claim["generation"]
        # The recovering parent dispatches, so it records its own identity for
        # cancel and reaping; seal mode starts no process (ADR 0019).
        with (delivery_cancel.parent_scope(attempt_dir, generation, attempt_id=attempt_id)
              if mode != "seal" else nullcontext()) as controller:
            try:
                _quarantine_checkpoints(envelope, attempt_dir, quarantine, claim["recovery_id"])
                state = ledger.snapshot(attempt_id)
                try:
                    # Seal mode only records what the run already decided, so it never
                    # runs the test: a bound digest is reused, otherwise tests are absent.
                    evidence = _rebuild_chartered_evidence(envelope, state, attempt_dir, test_runner,
                                                           run_test=mode != "seal")
                except (RecoveryRefused, ContractError):
                    if not recorded_failure:
                        raise
                    evidence = {"edit_evidence": None, "test_evidence": None}
                # Only grants a recovery released (this claim or an earlier one that
                # died before its regrant) may be re-granted.
                evidence["regrantable_action_ids"] = [item["action_id"] for item in state["actions"]
                                                      if item["reason"] == "recovery_unconsumed_grant"]
                if mode == "seal":
                    inputs = state.get("verifier_inputs", [])
                    verifier_sha = (hashlib.sha256(inputs[-1]["input"]["provider_task"].encode()).hexdigest()
                                    if inputs and evidence["edit_evidence"] else None)
                    result = _seal_attempt(envelope, attempt_dir, ledger, state, failure=outcome["failure"],
                                           edit_evidence=evidence["edit_evidence"], test_evidence=evidence["test_evidence"],
                                           verifier_input_sha256=verifier_sha, generation=generation,
                                           authority_guard=authority_guard, hook=seal_hook or (lambda point: None))
                    return {**result, "recovery_id": claim["recovery_id"], "mode": mode}
                job = envelope["job_contract"]
                if mode == "restart":
                    # A fresh start on the byte-identical envelope: Magentic replays
                    # every earlier manager call from the ledger (ADR 0017).
                    result = _execute_prepared_delivery(envelope, job["task"], attempt_dir, ledger,
                                                        manager_adapter=manager_adapter, worker_adapter=worker_adapter,
                                                        supervisor=supervisor, test_runner=test_runner, python_path=python_path,
                                                        resume=None, generation=generation, recovery=evidence,
                                                        seal_hook=seal_hook)
                    return {**result, "recovery_id": claim["recovery_id"], "mode": mode}
                row = next(item for item in state["actions"] if item["action_id"] == eligibility["action_id"])
                action = row["request"]
                checkpoint = ledger.read_magentic_checkpoint(attempt_id, "worker", action["action_id"])
                if checkpoint["metadata"]["checkpoint_id"] != action["checkpoint_id"]:
                    raise ContractError("Magentic restore checkpoint differs from worker action")
                resume: dict[str, Any] = {"checkpoint_id": action["checkpoint_id"],
                                          "request_id": f"flow-magentic-action-{action['sequence']}",
                                          "action_id": action["action_id"],
                                          **restore_position(envelope, state, checkpoint["metadata"]["ledger_seq"])}
                if mode == "answer" and row["status"] == "denied":
                    # The engineer denied this proposal's expansion; Magentic was told so.
                    resume["result"] = denied_reply(action["action_id"], row["reason"])
                elif mode == "answer":
                    reply = _completed_reply(ledger, envelope, attempt_dir, action, row["result"],
                                             is_verifier=action["instance_id"] in job["verifier_instance_ids"],
                                             is_producer=action["instance_id"] in job["producer_instance_ids"],
                                             edit_evidence=evidence["edit_evidence"], test_evidence=evidence["test_evidence"],
                                             generation=generation, authority_guard=authority_guard)
                    reply_path = attempt_dir / f"action-{action['action_id']}.result.json"
                    if not reply_path.exists():
                        _write_snapshot(reply_path, (canonical(reply) + "\n").encode())
                    resume["result"] = reply
                else:
                    resume["kind"] = "pending"
                result = _execute_prepared_delivery(envelope, job["task"], attempt_dir, ledger,
                                                    manager_adapter=manager_adapter, worker_adapter=worker_adapter,
                                                    supervisor=supervisor, test_runner=test_runner, python_path=python_path,
                                                    resume=resume, generation=generation, recovery=evidence,
                                                    seal_hook=seal_hook)
                return {**result, "recovery_id": claim["recovery_id"], "mode": mode}
            except Exception as exc:
                # A cancel can land before the run starts, in the evidence
                # rebuild's targeted test: seal or interrupt the same way.
                if controller is not None and controller.requested and controller.armed:
                    return delivery_termination.stop_on_cancel(envelope, attempt_dir, ledger, generation=generation,
                                                               detail=str(exc))
                raise


def _check_chartered_evidence(envelope: dict[str, Any], snapshot: dict[str, Any], attempt_dir: Path) -> None:
    """Refuse worktree drift without writing anything or running the test."""
    plan = rebuild_chartered_evidence_plan(envelope, snapshot)
    worktree = Path(envelope["worktree"])
    if not plan["producer_completed"]:
        _verify_chartered_baseline(worktree, envelope)
        return
    baseline = json.loads((attempt_dir / "baseline.json").read_text())
    try:
        edit = _verify_chartered_edit(worktree, baseline, attempt_dir, envelope["job_contract"], record=False)
    except ContractError as exc:
        raise RecoveryRefused(WORKTREE_DRIFT, str(exc)) from exc
    if plan["diff_digest"] is not None and edit["diff_sha256"] != plan["diff_digest"]:
        raise RecoveryRefused(WORKTREE_DRIFT, "worktree diff differs from the bound verifier input")


def _unbound_checkpoints(envelope: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """List checkpoint files the ledger never bound; restoring beside them is ambiguous."""
    directory = Path(envelope["checkpoint_dir"])
    bound = {Path(item["path"]).name for item in snapshot.get("magentic_checkpoints", [])}
    if not directory.is_dir() or directory.is_symlink():
        return []
    return [{"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(directory.iterdir())
            if path.is_file() and not path.is_symlink() and path.name not in bound]


def _quarantine_checkpoints(envelope: dict[str, Any], attempt_dir: Path, files: list[dict[str, str]],
                            recovery_id: str) -> None:
    if not files:
        return
    parent = attempt_dir / "checkpoints-quarantine"
    if parent.is_symlink() or parent.exists() and not parent.is_dir():
        raise ContractError("checkpoint quarantine path is unsafe")
    parent.mkdir(mode=0o700, exist_ok=True)
    target = parent / recovery_id
    target.mkdir(mode=0o700)
    if parent.is_symlink() or target.is_symlink():
        raise ContractError("checkpoint quarantine path is unsafe")
    for item in files:
        source = Path(envelope["checkpoint_dir"]) / item["name"]
        if source.is_file() and not source.is_symlink():
            os.replace(source, target / item["name"])


def _verify_chartered_baseline(worktree: Path, envelope: dict[str, Any]) -> None:
    """Before any producer edit, the worktree must still equal the pinned baseline."""
    baseline = envelope["job_contract"]["baseline"]
    try:
        head = _git(worktree, "rev-parse", "HEAD")
        diff = _git(worktree, "diff", "HEAD", "--").encode()
        changed = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    except ContractError as exc:
        raise RecoveryRefused(WORKTREE_DRIFT, str(exc)) from exc
    if head != envelope["source_commit"] or (
            (changed or diff) if baseline["kind"] == "clean" else hashlib.sha256(diff).hexdigest() != baseline["diff_sha256"]):
        raise RecoveryRefused(WORKTREE_DRIFT, "worktree differs from the pinned baseline")


def _rebuild_chartered_evidence(envelope: dict[str, Any], snapshot: dict[str, Any], attempt_dir: Path,
                                test_runner: Callable[[Path], dict[str, Any]] | None, *,
                                run_test: bool = True) -> dict[str, Any]:
    """Re-verify the worktree and reuse bound test evidence; run the test at most once."""
    plan = rebuild_chartered_evidence_plan(envelope, snapshot)
    worktree = Path(envelope["worktree"])
    job = envelope["job_contract"]
    if not plan["producer_completed"]:
        _verify_chartered_baseline(worktree, envelope)
        return {"edit_evidence": None, "test_evidence": None}
    baseline = json.loads((attempt_dir / "baseline.json").read_text())
    try:
        edit = _verify_chartered_edit(worktree, baseline, attempt_dir, job)
    except ContractError as exc:
        raise RecoveryRefused(WORKTREE_DRIFT, str(exc)) from exc
    if plan["diff_digest"] is not None and edit["diff_sha256"] != plan["diff_digest"]:
        raise RecoveryRefused(WORKTREE_DRIFT, "worktree diff differs from the bound verifier input")
    if plan["test_digest"] is not None:
        # The bound verifier input already judged this evidence; never rerun it.
        tests = {"command": job["test"]["argv"], "status": "passed", "output_sha256": plan["test_digest"]}
    elif not run_test:
        tests = None
    else:
        scope = process_identity.current()
        tests = (test_runner or partial(_run_chartered_test, job=job,
                                        on_process_group=scope.register if scope else None))(worktree)
        try:
            unchanged = _verify_chartered_edit(worktree, baseline, attempt_dir, job) == edit
        except ContractError:
            unchanged = False
        if not unchanged:
            raise RecoveryRefused(WORKTREE_DRIFT, "targeted test changed the verified worktree diff")
    return {"edit_evidence": edit, "test_evidence": tests}


def resume_delivery(work_id: str, attempt_id: str, *, root: Path | None = None,
                    manager_adapter: Callable[..., dict[str, Any]] | None = None,
                    worker_adapter: Callable[..., dict[str, Any]] | None = None,
                    supervisor: Callable[..., dict[str, Any]] | None = None,
                    test_runner: Callable[[Path], dict[str, Any]] | None = None,
                    python_path: str | None = None,
                    continuation_epoch_id: str | None = None) -> dict[str, Any]:
    """Restore a paused attempt: v5 from its completed worker response, v8 per ADR 0016."""
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    attempt_dir = run_dir / "execution" / attempt_id
    if not attempt_dir.is_dir() or attempt_dir.is_symlink():
        raise ContractError("Magentic attempt directory is absent")
    peek = _peek_snapshot(run_dir / "execution" / "ledger.sqlite", attempt_id)
    if peek is not None and peek["execution_protocol_version"] == 9:
        # A provider send claim is never replayed by resume. Operators receive
        # the durable reconciliation state instead of a second dispatch.
        return v9_recovery_status(work_id, attempt_id, root=project_root)
    if peek is not None and peek["execution_protocol_version"] in {6, 7, 8}:
        if continuation_epoch_id:
            raise RecoveryRefused(CONTINUATION_EPOCHS_V5_ONLY)
        return _resume_chartered(work_id, attempt_id, root=project_root, manager_adapter=manager_adapter,
                                 worker_adapter=worker_adapter, supervisor=supervisor, test_runner=test_runner,
                                 python_path=python_path, actor="flow-chartered-resume")
    ledger = ExecutionLedger(run_dir / "execution" / "ledger.sqlite")
    snapshot = ledger.snapshot(attempt_id)
    envelope = snapshot["envelope"]
    expected_status = "unknown" if continuation_epoch_id else "started"
    if snapshot["status"] != expected_status or snapshot["execution_protocol_version"] != 5 or envelope["work_id"] != work_id:
        raise ContractError("Magentic attempt is closed or differs from the approved run")
    if continuation_epoch_id:
        epoch = ledger.continuation_snapshot(continuation_epoch_id)
        if epoch["attempt_id"] != attempt_id or epoch["status"] != "pending":
            raise ContractError("Magentic continuation differs from resolved attempt")
    if json.loads((attempt_dir / "envelope.json").read_text()) != envelope:
        raise ContractError("stored Magentic envelope changed")
    manager_calls = snapshot.get("manager_calls", [])
    if any(item["status"] in {"started", "unknown"} for item in manager_calls + snapshot["actions"]):
        raise ContractError("Magentic send outcome requires reconciliation")
    completed = [item for item in snapshot["actions"] if item["status"] == "completed"]
    if not completed:
        raise ContractError("Magentic has no completed worker action to restore")
    last = completed[-1]
    action = last["request"]
    checkpoint = ledger.read_magentic_checkpoint(attempt_id, "worker", action["action_id"])
    recorded = checkpoint["metadata"]
    if recorded["checkpoint_id"] != action["checkpoint_id"]:
        raise ContractError("Magentic restore checkpoint differs from worker action")
    reply_path = attempt_dir / f"action-{action['action_id']}.result.json"
    if reply_path.is_symlink():
        raise ContractError("durable Magentic worker response path is unsafe")
    if reply_path.is_file():
        reply = json.loads(reply_path.read_text())
    else:
        output = last["result"]["output"]
        summary = output
        if action["provider"] == "claude":
            baseline = json.loads((attempt_dir / "baseline.json").read_text())
            edit = _verify_edit(Path(envelope["worktree"]), baseline, attempt_dir)
            (test_runner or _run_targeted_test)(Path(envelope["worktree"]))
            summary += ("\n\nFlow verified the scoped repair. Diff SHA-256: " + edit["diff_sha256"]
                        + ". Targeted test: passed. Verified diff excerpt:\n" + (attempt_dir / "repair.diff").read_text()[:2048])
        reply = {"status": "completed", "action_id": action["action_id"], "summary": summary, "output": output}
        _write_snapshot(reply_path, (canonical(reply) + "\n").encode())
    if reply.get("action_id") != action["action_id"] or reply.get("output") != last["result"]["output"]:
        raise ContractError("durable Magentic worker response differs from ledger")
    committed = {item["call_id"] for item in manager_calls if item["status"] == "completed"}
    before_pause = {item["action_id"] for item in snapshot["events"]
                    if item["event"] == "manager_response_observed" and item["seq"] <= recorded["ledger_seq"]}
    manager_calls_committed = len(committed & before_pause)
    if manager_calls_committed < 1:
        raise ContractError("Magentic checkpoint lacks observed manager decisions")
    replan_events = {item["action_id"] for item in snapshot["events"]
                     if item["event"] == "replan_allowed" and item["seq"] <= recorded["ledger_seq"]}
    approved_replans = [item for item in snapshot["replans"]
                        if item["status"] == "allowed" and item["replan_id"] in replan_events]
    replans_committed = len(approved_replans)
    if replans_committed > envelope["limits"]["max_replans"] or sorted(item["sequence"] for item in approved_replans) != list(range(1, replans_committed + 1)):
        raise ContractError("Magentic checkpoint replan lineage is inconsistent")
    for replan in approved_replans:
        phases = {item["request"]["phase"] for item in manager_calls
                  if item["status"] == "completed" and item["call_id"] in before_pause
                  and item["request"].get("replan_id") == replan["replan_id"]}
        if phases != {"replan_facts", "replan_plan"}:
            raise ContractError("Magentic checkpoint lacks a completed replan pair")
    resume = {"checkpoint_id": recorded["checkpoint_id"],
              "request_id": f"flow-magentic-action-{action['sequence']}",
              "action_id": action["action_id"], "manager_calls_committed": manager_calls_committed,
              "replans_committed": replans_committed,
              "result": reply}
    task = (attempt_dir / "job-charter.snapshot.md").read_text()
    if continuation_epoch_id:
        epoch_generation = ledger.claim_continuation(continuation_epoch_id, actor="flow-magentic-recovery")
        ledger.start_magentic_continuation(continuation_epoch_id, generation=epoch_generation)
    generation = ledger.claim_recovery(attempt_id, actor="flow-magentic-resume")
    return _execute_prepared_delivery(envelope, task, attempt_dir, ledger,
                                      manager_adapter=manager_adapter, worker_adapter=worker_adapter,
                                      supervisor=supervisor, test_runner=test_runner, python_path=python_path,
                                      resume=resume, generation=generation,
                                      continuation_epoch_id=continuation_epoch_id)


def resolve_execution(work_id: str, attempt_id: str, action_id: str, actor: str, disposition: str, explanation: str,
                      evidence_file: str | None = None, expected_generation: int | None = None, *,
                      root: Path | None = None) -> dict[str, Any]:
    """Record one operator resolution: v8 through the fenced chartered route, v5-v7 unchanged."""
    project_root = (root or repo_root()).resolve()
    peek = _peek_snapshot(project_root / ".flow" / "runs" / work_id / "execution" / "ledger.sqlite", attempt_id)
    if peek is not None and peek["execution_protocol_version"] == 8:
        return _resolve_chartered(work_id, attempt_id, action_id, actor, disposition, explanation,
                                  evidence_file=evidence_file, expected_generation=expected_generation, root=project_root)
    if evidence_file is None:
        raise RecoveryRefused(EVIDENCE_FILE_REQUIRED)
    if expected_generation is not None:
        raise RecoveryRefused(EXPECTED_GENERATION_V8_ONLY)
    return resolve_attempt(work_id, attempt_id, action_id, actor, disposition, explanation, evidence_file, root=root)


def _resolve_chartered(work_id: str, attempt_id: str, action_id: str, actor: str, disposition: str,
                       explanation: str, *, evidence_file: str | None, expected_generation: int | None,
                       root: Path) -> dict[str, Any]:
    """Resolve one v8 action from Flow's stored response observation (ADR 0016, chunk 2).

    Only Flow's own observation is evidence, so an operator file is refused.
    The route holds the recovery lock, so it refuses while a live run holds
    the attempt, and every check before the ledger write is read-only.
    """
    if evidence_file is not None:
        raise RecoveryRefused(V8_EVIDENCE_FILE_REFUSED, "v8 resolves only from Flow's stored response observation")
    if expected_generation is None:
        raise RecoveryRefused(EXPECTED_GENERATION_REQUIRED, "pass the owner generation shown by inspect-delivery")
    if disposition != "resolved_completed":
        raise RecoveryRefused(V8_DISPOSITION_UNSUPPORTED, "v8 accepts only resolved_completed")
    run_dir = root / ".flow" / "runs" / work_id
    ledger_path = run_dir / "execution" / "ledger.sqlite"
    with ExecutionLedger(ledger_path, read_only=True).recovery_lock(attempt_id, holder="recovery"):
        snapshot = _peek_snapshot(ledger_path, attempt_id)
        attempt_dir = run_dir / "execution" / attempt_id
        if snapshot is None or not attempt_dir.is_dir() or attempt_dir.is_symlink():
            raise ContractError("chartered attempt is absent")
        envelope = snapshot["envelope"]
        envelope_path = attempt_dir / "envelope.json"
        if (envelope["work_id"] != work_id or not envelope_path.is_file() or envelope_path.is_symlink()
                or json.loads(envelope_path.read_text()) != envelope):
            raise RecoveryRefused(ENVELOPE_CHANGED)
        if snapshot["status"] != "started":
            raise RecoveryRefused(ATTEMPT_TERMINAL)
        try:
            delivery = json.loads((run_dir / "run.json").read_text()).get("delivery")
        except (OSError, json.JSONDecodeError):
            delivery = None
        if not lead_claim_active(delivery, envelope):
            raise RecoveryRefused(LEAD_GENERATION_INACTIVE)
        _refuse_project_flow_in_worktree(Path(envelope["worktree"]), root)
        if snapshot["owner_generation"] != expected_generation:
            raise RecoveryRefused(OWNER_GENERATION_STALE, f"owner generation is {snapshot['owner_generation']}")
        with delivery_authority_guard(run_dir, envelope):
            return ExecutionLedger(ledger_path).resolve_observed_v8(
                attempt_id, action_id, actor, explanation, expected_generation=expected_generation,
                expected_event_seq=snapshot["events"][-1]["seq"] if snapshot["events"] else 0)


def decide_expansion(work_id: str, attempt_id: str, request_id: str, *, approve: bool, expected_generation: int,
                     actor: str, explanation: str, root: Path | None = None) -> dict[str, Any]:
    """Approve or deny one pending expansion request of a paused v8 attempt (ADR 0017).

    Locks follow ADR 0016: the attempt's recovery fence (so no live run or
    recovery owns it), the run authority guard (so the lead claim is the one
    the attempt runs under), the send lock, then SQLite. Resuming is a
    separate, explicit ``recover-delivery-lead``.
    """
    project_root = (root or repo_root()).resolve()
    valid, _, findings = validate_orchestration(work_id, "dispatch", root=project_root)
    if not valid:
        raise ContractError("orchestration dispatch invalid: " + "; ".join(f.message for f in findings))
    run_dir = project_root / ".flow" / "runs" / work_id
    ledger_path = run_dir / "execution" / "ledger.sqlite"
    if not ledger_path.is_file() or ledger_path.is_symlink():
        raise ContractError("delivery execution ledger is absent")
    ledger = ExecutionLedger(ledger_path)
    envelope = ledger.snapshot(attempt_id)["envelope"]
    if envelope.get("execution_protocol_version") != 8 or envelope.get("work_id") != work_id:
        raise ContractError("expansion decisions require a protocol v8 attempt of this run")
    with ExitStack() as fences:
        try:
            fences.enter_context(ledger.recovery_lock(attempt_id, holder="decide"))
        except RecoveryRefused as exc:
            raise RecoveryRefused(ATTEMPT_NOT_PAUSED, f"the attempt fence is held ({exc.reason})") from None
        try:
            fences.enter_context(delivery_authority_guard(run_dir, envelope))
        except DeliveryControlError as exc:
            raise RecoveryRefused(LEAD_GENERATION_INACTIVE, str(exc)) from None
        fences.enter_context(ledger.send_lock())
        return ledger.decide_expansion(attempt_id, request_id, approve=approve, expected_generation=expected_generation,
                                       actor=actor, explanation=explanation)


def recover_delivery(work_id: str, attempt_id: str, *, actor: str, root: Path | None = None,
                     python_path: str | None = None,
                     manager_adapter: Callable[..., dict[str, Any]] | None = None,
                     worker_adapter: Callable[..., dict[str, Any]] | None = None,
                     supervisor: Callable[..., dict[str, Any]] | None = None,
                     test_runner: Callable[[Path], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Resolve one observed v5 Claude result and resume it; route v6-v8 to chartered recovery.

    ``actor`` is required: it is recorded on the recovery and as the owner actor (ADR 0020).
    """
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 256:
        raise ContractError("recovery actor is required")
    project_root = (root or repo_root()).resolve()
    valid, _, findings = validate_orchestration(work_id, "dispatch", root=project_root)
    if not valid:
        raise ContractError("orchestration dispatch invalid: " + "; ".join(f.message for f in findings))
    attempt_dir = project_root / ".flow" / "runs" / work_id / "execution" / attempt_id
    peek = _peek_snapshot(attempt_dir.parent / "ledger.sqlite", attempt_id)
    if peek is not None and peek["execution_protocol_version"] == 9:
        return v9_recovery_status(work_id, attempt_id, root=project_root)
    if peek is not None and peek["execution_protocol_version"] in {6, 7, 8}:
        # Chunk 1 needs no operator evidence, so v8 recover equals resume.
        return _resume_chartered(work_id, attempt_id, root=project_root, manager_adapter=manager_adapter,
                                 worker_adapter=worker_adapter, supervisor=supervisor, test_runner=test_runner,
                                 python_path=python_path, actor=actor)
    ledger = ExecutionLedger(attempt_dir.parent / "ledger.sqlite")
    snapshot = ledger.snapshot(attempt_id)
    envelope = snapshot["envelope"]
    receipt_path = attempt_dir / "receipt.json"
    event_path = attempt_dir / "claude-implementer.events.ndjson"
    if (snapshot["status"] != "unknown" or snapshot["execution_protocol_version"] != 5
            or envelope["work_id"] != work_id or snapshot["receipt_path"] != str(receipt_path)):
        raise ContractError("Magentic recovery requires the exact unknown terminal attempt")
    for path in (attempt_dir, receipt_path, event_path, attempt_dir.parent / "ledger.sqlite"):
        mode = path.lstat()
        if path.is_symlink() or mode.st_uid != os.getuid() or mode.st_mode & 0o077:
            raise ContractError("Magentic recovery requires owner-only local evidence")
    original = json.loads(receipt_path.read_text())
    validate_receipt(envelope, original)
    if original["status"] != "unknown" or original["attempt_id"] != attempt_id:
        raise ContractError("original Magentic receipt differs from terminal attempt")
    candidates = [item for item in snapshot["actions"] if item["request"]["assignment_id"] == "claude-implementer"
                  and item["status"] in {"unknown", "completed"}]
    if len(candidates) != 1 or any(item["status"] == "unknown" for item in snapshot["actions"] if item != candidates[0]) or any(
            item["status"] in {"started", "unknown"} for item in snapshot["manager_calls"]):
        raise ContractError("Magentic recovery requires one unknown Claude implementer")
    selected = candidates[0]
    action = selected["request"]
    events = event_path.read_bytes()
    trace = original["evidence"].get("event_trace")
    if (not trace or trace["path"] != event_path.name or trace["bytes"] != len(events)
            or hashlib.sha256(events).hexdigest() != trace["sha256"]):
        raise ContractError("Claude event trace differs from terminal receipt")
    result = _stream_result(events, action["model"])
    validate_result(envelope, result, action=action)
    checkpoint = ledger.read_magentic_checkpoint(attempt_id, "worker", action["action_id"])
    checkpoint_sha = checkpoint["metadata"]["file_sha256"]
    baseline = json.loads((attempt_dir / "baseline.json").read_text())
    worktree = Path(envelope["worktree"])
    if _git(worktree, "rev-parse", "HEAD") != envelope["source_commit"]:
        raise ContractError("recovery worktree source commit changed")
    edit = _verify_edit(worktree, baseline, attempt_dir)
    (test_runner or _run_targeted_test)(worktree)
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    evidence = [{"kind": kind, "path": str(path.relative_to(project_root)),
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for kind, path in
                (("provider_event_trace", event_path), ("original_receipt", receipt_path),
                 ("magentic_checkpoint", Path(checkpoint["metadata"]["path"])),
                 ("verified_repair_diff", Path(edit["diff_path"]))) ]
    if selected["status"] == "unknown":
        generation = ledger.claim_recovery(attempt_id, actor=actor)
        ledger.observe_response(action["action_id"], result, generation)
        resolution = ledger.resolve_unknown(attempt_id, action["action_id"], actor,
                                            "resolved_completed", "Validated terminal Claude CLI result and scoped repair test",
                                            evidence, generation=generation)
    else:
        matches = [item for item in snapshot["resolutions"] if item["action_id"] == action["action_id"]
                   and item["disposition"] == "resolved_completed" and item["result"] == result
                   and item["evidence"] == evidence]
        if len(matches) != 1:
            raise ContractError("completed Claude action lacks matching prior recovery resolution")
        resolution = matches[0]
    epoch = ledger.begin_continuation(attempt_id, action["action_id"], resolution["resolution_id"],
                                      receipt_sha, checkpoint_sha, actor=actor)
    return resume_delivery(work_id, attempt_id, root=project_root, manager_adapter=manager_adapter,
                           worker_adapter=worker_adapter, supervisor=supervisor, test_runner=test_runner,
                           python_path=python_path, continuation_epoch_id=epoch["epoch_id"])


# One builder, shared with verify-receipt (ADR 0020).
_verifier_provider_task = verifier_provider_task


def _evaluate_verifier(ledger: ExecutionLedger, action: dict[str, Any], result: dict[str, Any],
                       binding: dict[str, Any], *, generation: int) -> dict[str, Any]:
    """Record Flow's judgment of an already completed verifier response."""
    evaluation = evaluate_candidate(
        action_id=action["action_id"], verifier_input_digest=binding["input_digest"],
        raw_output=result["output"], diff_digest=binding["diff_digest"],
        test_evidence_digest=binding["test_digest"],
        forced_unusable_reason="provider_binding_mismatch" if provider_binding_mismatch(action, result) else None)
    return ledger.record_verifier_evaluation(action["action_id"], evaluation, generation=generation)["evaluation"]


def _verifier_summary(ledger: ExecutionLedger, attempt_id: str, evaluation: dict[str, Any], output: str) -> str:
    usage = ledger.verifier_usage(attempt_id)
    return ("Flow verifier evaluation: " + evaluation["disposition"]
            + "; reason: " + evaluation["reason"]
            + "; retry eligible: " + str(usage["retry_eligible"]).lower()
            + ". Provider summary: " + output)


def _producer_summary(output: str, edit_evidence: dict[str, Any], attempt_dir: Path) -> str:
    return (output + "\n\nFlow verified the scoped repair. Diff SHA-256: " + edit_evidence["diff_sha256"]
            + ". Targeted test: passed. Verified diff excerpt:\n" + (attempt_dir / "repair.diff").read_text()[:2048])


def _completed_reply(ledger: ExecutionLedger, envelope: dict[str, Any], attempt_dir: Path,
                     action: dict[str, Any], result: dict[str, Any], *, is_verifier: bool, is_producer: bool,
                     edit_evidence: dict[str, Any] | None, test_evidence: dict[str, Any] | None,
                     generation: int, authority_guard: Callable[[], Any]) -> dict[str, Any]:
    """Rebuild the reply for an already completed action; it never resends."""
    reply_path = attempt_dir / f"action-{action['action_id']}.result.json"
    if reply_path.is_file() and not reply_path.is_symlink():
        reply = json.loads(reply_path.read_text())
        if reply.get("action_id") == action["action_id"] and reply.get("output") == result["output"]:
            return reply
    aid = envelope["attempt_id"]
    if envelope["execution_protocol_version"] == 8 and is_verifier:
        # A crash can land between completion and evaluation. Replay
        # re-evaluates the stored response; it never resends.
        replay_state = ledger.snapshot(aid)
        binding = next((item for item in replay_state.get("verifier_inputs", [])
                        if item["action_id"] == action["action_id"]), None)
        if binding is None:
            raise ContractError("completed structured verifier has no durable input binding")
        evaluation = next((item["evaluation"] for item in replay_state.get("verifier_evaluations", [])
                           if item["action_id"] == action["action_id"]), None)
        if evaluation is None:
            with authority_guard():
                evaluation = _evaluate_verifier(ledger, action, result, binding, generation=generation)
        summary = _verifier_summary(ledger, aid, evaluation, result["output"])
    elif is_producer and edit_evidence and test_evidence:
        summary = _producer_summary(result["output"], edit_evidence, attempt_dir)
    else:
        summary = result["output"]
    return {"status": "completed", "action_id": action["action_id"],
            "summary": summary, "output": result["output"]}


def _build_receipt(envelope: dict[str, Any], attempt_dir: Path, ledger: ExecutionLedger,
                   snapshot: dict[str, Any], *, failure: str, edit_evidence: dict[str, Any] | None,
                   test_evidence: dict[str, Any] | None, verifier_input_sha256: str | None,
                   continuation_epoch_id: str | None, blocks: dict[str, Any] | None = None) -> tuple[dict[str, Any], str, str]:
    """Derive the terminal status and the linked receipt from ledger facts."""
    aid = envelope["attempt_id"]
    source_commit = envelope["source_commit"]
    worktree = Path(envelope["worktree"])
    baseline = json.loads((attempt_dir / "baseline.json").read_text())
    chartered = envelope["execution_protocol_version"] in {6, 7, 8}
    delivery_protocol = envelope["execution_protocol_version"] in {7, 8}
    structured_verifier = envelope["execution_protocol_version"] == 8
    job = envelope.get("job_contract") if chartered else None
    actions = snapshot["actions"]
    manager_calls = snapshot.get("manager_calls", [])
    uncertain = any(item["status"] in {"started", "unknown"} for item in actions + manager_calls)
    producer = [item for item in actions if (item["request"]["instance_id"] in job["producer_instance_ids"] if chartered else item["request"]["assignment_id"] == "claude-implementer") and item["status"] == "completed"]
    verifier = [item for item in actions if (item["request"]["instance_id"] in job["verifier_instance_ids"] if chartered else item["request"]["assignment_id"] == "local-verifier") and item["status"] == "completed"]
    verified_order = bool(producer and any(item["request"]["sequence"] > producer[0]["request"]["sequence"] for item in verifier))
    final_evaluation = (snapshot.get("verifier_evaluations") or [{}])[-1].get("evaluation")
    structured_pass = (not structured_verifier or bool(final_evaluation)
                       and final_evaluation["disposition"] == "valid_pass")
    if (structured_pass and structured_verifier and not failure and edit_evidence and test_evidence
            and (final_evaluation["diff_digest"] != edit_evidence["diff_sha256"]
                 or final_evaluation["test_evidence_digest"] != test_evidence["output_sha256"])):
        # The pass judged evidence Flow no longer holds; it cannot complete.
        structured_pass = False
        failure = "structured verifier pass is bound to stale evidence"
    terminal = "unknown" if uncertain else ("completed" if not failure and producer and verified_order and structured_pass and edit_evidence and test_evidence else "failed")
    if terminal == "failed" and not failure:
        if structured_verifier and final_evaluation:
            failure = "structured verifier ended " + final_evaluation["disposition"]
        elif not producer:
            failure = "no producer result was completed"
        elif not verified_order:
            failure = "no verifier completed after the producer"
        elif not edit_evidence or not test_evidence:
            failure = "Flow did not capture complete edit and test evidence"
        else:
            failure = "delivery manager did not produce an acceptable handback"
    reason = "reconciliation_required" if terminal == "unknown" else failure
    receipt = {"schema_version": 1, "execution_protocol_version": envelope["execution_protocol_version"], "work_id": envelope["work_id"], "attempt_id": aid,
               "envelope_digest": envelope_digest(envelope), "charter_digest": envelope["charter_digest"],
               "manifest_digest": envelope["manifest_digest"], "charter_sources": envelope["charter_sources"],
               "run_protocol_revision": 2, "roster": envelope["roster"], "status": terminal, "reason": reason,
               "manager_calls": manager_calls, "actions": actions, "replans": snapshot["replans"],
               "checkpoints": snapshot.get("magentic_checkpoints", []),
               "failure_detail": failure[:512],
               "evidence": {"source_commit": source_commit, "worktree": str(worktree),
                            "allowed_paths": envelope["allowed_paths"], "baseline": baseline,
                            "edit": edit_evidence, "tests": test_evidence,
                            "verifier_input_sha256": verifier_input_sha256}, "created_at": utc_now()}
    if structured_verifier:
        receipt["verifier_inputs"] = snapshot.get("verifier_inputs", [])
        receipt["verifier_evaluations"] = snapshot.get("verifier_evaluations", [])
        receipt["verifier_usage"] = snapshot["verifier_usage"]
        # The seal's own blocks, read with the snapshot under the sealing lock (ADR 0020).
        if blocks is None:
            raise ContractError("a v8 receipt is built from the sealing seal_view")
        if blocks["lineage_usage"] is not None:
            receipt["lineage_usage"] = blocks["lineage_usage"]
        if blocks["expansion"] is not None:
            # Added only when the lineage expanded, so other receipts stay byte-identical.
            receipt["expansion"] = blocks["expansion"]
        if blocks["manager_progress"] is not None:
            # Added only when a progress reply was repaired or retried (ADR 0018).
            receipt["manager_progress"] = blocks["manager_progress"]
        if blocks["token_usage"] is not None:
            receipt["token_usage"] = blocks["token_usage"]
        if snapshot.get("recoveries"):
            # A receipt on disk while the attempt is started is an unsealed
            # draft from a process that died before finish_attempt.
            draft = attempt_dir / "receipt.json"
            replaced = (hashlib.sha256(draft.read_bytes()).hexdigest()
                        if snapshot["status"] == "started" and draft.is_file() and not draft.is_symlink() else None)
            receipt["recovery"] = build_recovery_block(snapshot, replaced_draft_sha256=replaced)
    if delivery_protocol:
        receipt.update({field: envelope[field] for field in ("shaper_contract_digest", "delivery_charter_digest",
                                                              "handoff_digest", "delivery_lead_claim_digest", "delivery_lead_claim")})
    if "maf_runtime" in envelope:
        receipt["maf_runtime"] = envelope["maf_runtime"]
    trace_path = attempt_dir / "claude-implementer.debug.log"
    if trace_path.is_file() and not trace_path.is_symlink():
        trace_size = trace_path.stat().st_size
        if trace_size > MAX_TRACE_BYTES:
            raise ContractError("Claude diagnostic trace exceeds limit")
        receipt["evidence"]["diagnostic_trace"] = {
            "path": trace_path.name, "sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
            "bytes": trace_size}
    event_path = attempt_dir / "claude-implementer.events.ndjson"
    if event_path.is_file() and not event_path.is_symlink():
        event_size = event_path.stat().st_size
        receipt["evidence"]["event_trace"] = {
            "path": event_path.name, "sha256": _stream_sha256(event_path),
            "bytes": event_size}
    if continuation_epoch_id:
        epoch = ledger.continuation_snapshot(continuation_epoch_id)
        receipt["evidence"]["continuation"] = {
            "epoch_id": continuation_epoch_id,
            "original_receipt_sha256": epoch["receipt_sha256"],
            "checkpoint_sha256": epoch["checkpoint_sha256"],
            "resolution_id": epoch["resolution_id"]}
    return receipt, terminal, reason


def _execution_facts(envelope: dict[str, Any], job: dict[str, Any] | None, source_commit: str) -> str:
    chartered = envelope["execution_protocol_version"] in {6, 7, 8}
    structured_verifier = envelope["execution_protocol_version"] == 8
    return ("\n\nFlow-verified execution facts:\n"
            "- The isolated worktree is pinned to source commit " + source_commit + ".\n"
            + (("- The approved baseline is " + job["baseline"]["kind"] + ".\n") if chartered else "- The approved regression test is already present and failed before this job's first provider send. Do not ask a specialist to create or rerun that prerequisite.\n")
            + "- Read-only analyst and verifier specialists can analyze supplied task text only; they cannot read files,"
            " run commands, or edit the worktree.\n"
            "- The approved editor may edit only the charter's allowed paths. Flow verifies the diff and runs"
            " the targeted test after that edit; the full suite is an acceptance check.\n"
            + ("- The editor sandbox cannot write linked Git metadata. Do not ask the editor to commit or push,"
               " and do not treat a missing editor-side commit as incomplete work. Flow owns the verified-diff"
               " handback; repository integration happens only after Flow accepts that handback.\n" if chartered else "")
            + ("- A protocol-v8 request is not satisfied until Flow reports a verifier valid_pass bound to the"
               " current diff and test evidence. When a verifier still needs to run, set is_request_satisfied to"
               " false and select that verifier; never mark the request satisfied in the same decision.\n"
               if structured_verifier else "")
            + ("- The approved editors get one call in total; Flow refuses any second editor call. That call must"
               " read what it needs and make the complete edit in the same turn. Never delegate an inspect-only or"
               " \"do not edit yet\" step to an editor: Flow checks the worktree right after it, and no edit fails"
               " the attempt.\n" if chartered else "")
            + "".join(f"- Predecessor attempt {item['attempt_id']} ended {item['terminal_status']} under lead"
                      f" generation {item['lead_generation']}; its evidence is not reused.\n"
                      for item in envelope.get("predecessors", [])))


def _execute_prepared_delivery(envelope: dict[str, Any], task: str, attempt_dir: Path,
                               ledger: ExecutionLedger, **kwargs: Any) -> dict[str, Any]:
    """Run one prepared attempt; a live v8 run holds the attempt's recovery fence throughout."""
    if envelope["execution_protocol_version"] == 8 and kwargs.get("recovery") is None:
        with ledger.recovery_lock(envelope["attempt_id"], holder="live"), \
                delivery_cancel.parent_scope(attempt_dir, kwargs["generation"],
                                             attempt_id=envelope["attempt_id"]):
            return _run_prepared_delivery(envelope, task, attempt_dir, ledger, **kwargs)
    return _run_prepared_delivery(envelope, task, attempt_dir, ledger, **kwargs)


def _run_prepared_delivery(envelope: dict[str, Any], task: str, attempt_dir: Path,
                               ledger: ExecutionLedger, *,
                               manager_adapter: Callable[..., dict[str, Any]] | None,
                               worker_adapter: Callable[..., dict[str, Any]] | None,
                               supervisor: Callable[..., dict[str, Any]] | None,
                               test_runner: Callable[[Path], dict[str, Any]] | None,
                               python_path: str | None,
                               resume: dict[str, Any] | None = None,
                               generation: int = 1,
                               continuation_epoch_id: str | None = None,
                               seal_hook: Callable[[str], None] | None = None,
                               recovery: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run one attempt behind Flow's callbacks and seal its receipt.

    ``recovery`` carries evidence a v8 recovery rebuilt; it replaces the live
    preamble so the targeted test is not rerun, and it enables re-granting
    grants the recovery claim released.

    ``seal_hook`` is a test seam only: it is called at ``after-runtime-outcome``,
    ``after-receipt-draft``, and ``before-finish-attempt`` so a test can
    simulate a process death at each sealing boundary.
    """
    aid = envelope["attempt_id"]
    hook = seal_hook or (lambda point: None)
    work_id = envelope["work_id"]
    source_commit = envelope["source_commit"]
    worktree = Path(envelope["worktree"])
    baseline = json.loads((attempt_dir / "baseline.json").read_text())
    chartered = envelope["execution_protocol_version"] in {6, 7, 8}
    delivery_protocol = envelope["execution_protocol_version"] in {7, 8}
    structured_verifier = envelope["execution_protocol_version"] == 8
    authority_guard = (lambda: delivery_authority_guard(attempt_dir.parents[1], envelope)) if delivery_protocol else nullcontext
    job = envelope.get("job_contract") if chartered else None
    task += _execution_facts(envelope, job, source_commit)
    # Only Flow's own adapters start processes; each registers its group with
    # the parent's control record (ADR 0019). Injected adapters are unchanged.
    scope = process_identity.current() if structured_verifier else None
    register = scope.register if scope is not None else None
    # SIGTERM only sets a flag (ADR 0019); every authorization checks it first.
    controller = delivery_cancel.current() if structured_verifier else None
    stop_if_cancelled = controller.check if controller is not None else (lambda: None)
    manager_adapter = manager_adapter or partial(_default_manager_adapter, on_process_group=register)
    worker_adapter = worker_adapter or partial(_default_worker_adapter, trace_dir=attempt_dir, on_process_group=register)
    test_runner = test_runner or (partial(_run_chartered_test, job=job, on_process_group=register) if chartered
                                  else _run_targeted_test)
    verify_edit = (partial(_verify_chartered_edit, job=job) if chartered else _verify_edit)
    edit_evidence: dict[str, Any] | None = None
    test_evidence: dict[str, Any] | None = None
    failure = ""
    failure_exception: Exception | None = None
    recoverable_transport_failure = False
    verifier_input_sha256: str | None = None
    initial_snapshot = ledger.snapshot(aid)
    if recovery is not None:
        edit_evidence, test_evidence = recovery["edit_evidence"], recovery["test_evidence"]
    elif any((item["request"]["instance_id"] in job["producer_instance_ids"] if chartered else item["request"]["assignment_id"] == "claude-implementer") and item["status"] == "completed"
           for item in initial_snapshot["actions"]):
        edit_evidence = verify_edit(worktree, baseline, attempt_dir)
        test_evidence = test_runner(worktree)
    prior_verifier = [item for item in initial_snapshot["actions"]
                      if (item["request"]["instance_id"] in job["verifier_instance_ids"] if chartered else item["request"]["assignment_id"] == "local-verifier") and item["status"] == "completed"]
    if prior_verifier and edit_evidence:
        verifier_task = _verifier_provider_task(
            prior_verifier[-1]["request"]["task"], (attempt_dir / "repair.diff").read_text(),
            edit_evidence["diff_sha256"], structured=structured_verifier,
            test_output=(test_evidence or {}).get("output_excerpt", ""),
            authority_statement=VERIFIED_HANDOFF_AUTHORITY)
        verifier_input_sha256 = hashlib.sha256(verifier_task.encode()).hexdigest()

    manager_provider = (envelope.get("manager") or {}).get("provider", "claude") if structured_verifier else None

    def on_manager(message: dict[str, Any]) -> str:
        stop_if_cancelled()
        request = _normalized_manager_request(envelope, message)
        if request["phase"] == "replan_facts":
            replan = {"schema_version": 1, "kind": "replan", "attempt_id": aid,
                      "envelope_digest": envelope_digest(envelope), "sequence": request["replan_sequence"],
                      "proposal": {"prompt_digest": request["prompt_digest"]}}
            replan["replan_id"] = request["replan_id"]
            with authority_guard():
                decision = ledger.decide_replan(envelope, replan, generation=generation)
            if not decision["allowed"]:
                raise ContractError("Magentic replan denied: " + decision["reason"])
        with authority_guard():
            decision = ledger.decide_manager_call(envelope, request, generation=generation)
            if recovery is not None and decision.get("replayed") and decision["allowed"]:
                # A replayed, never-sent grant would expire when consumed.
                decision = ledger.reissue_recovered_manager_grant(request["call_id"], generation=generation)
            elif (recovery is not None and decision.get("replayed") and not decision["allowed"]
                    and decision.get("result") is None
                    and (decision.get("expansion") or {}).get("status") == "granted"):
                # The paused call is back under its own identity: allow it once.
                # A replayed call that already completed (for example one granted
                # from charter headroom) keeps its recorded answer instead.
                decision = ledger.reissue_expanded_manager_grant(request["call_id"], generation=generation)
        if decision.get("replayed") and isinstance(decision.get("result"), dict):
            observed = decision["result"].get("output")
            if isinstance(observed, str) and observed.strip():
                return observed
        paused = _pending_expansion(decision)
        if paused:
            # No text can answer a call Flow refused; the runner stops here and
            # recovery replays this call once the engineer decides (ADR 0017).
            raise ExpansionPaused(paused)
        if decision.get("replayed") and not decision["allowed"]:
            raise ContractError("Magentic manager call needs reconciliation: " + decision["reason"])
        if not decision["allowed"]:
            raise ContractError("Magentic manager call denied: " + decision["reason"])
        with authority_guard(), ledger.send_lock():
            ledger.assert_owner(aid, generation)
            if structured_verifier:
                # The exact request is durable before its grant can be used, so
                # every call that might have been sent has its file (ADR 0020).
                write_request_file(attempt_dir, request["call_id"],
                                   request_bytes(request["call_id"], request["prompt_digest"], message["messages"]))
            stop_if_cancelled()  # before the grant is used, so an unsent call stays unsent
            if not ledger.consume_manager_grant(request["call_id"], decision["grant_id"], generation=generation):
                raise ContractError("Magentic manager grant was already consumed")
            try:
                result = manager_adapter(message, envelope=envelope, workspace=worktree)
                text = result.get("output") if isinstance(result, dict) else None
                if not isinstance(text, str) or not text.strip() or len(text.encode()) > 32768:
                    raise ContractError("manager adapter returned invalid model text")
                observation = {"status": "completed", "output": text,
                               "output_sha256": digest(text),
                               "usage": result.get("usage")}
                if structured_verifier and manager_provider in MANAGER_IDENTITY_FIELDS:
                    # The provider session identity joins the call to its
                    # provider transcript; a reply without it stays uncertain.
                    for field in MANAGER_IDENTITY_FIELDS[manager_provider]:
                        observation[field] = result.get(field)
                    validate_manager_identity(manager_provider, observation)
                if result.get("normalization") == "exact_json_fence":
                    observation["normalization"] = "exact_json_fence"
                    observation["raw_output_sha256"] = result["raw_output_sha256"]
                ledger.observe_manager_response(request["call_id"], observation, generation=generation)
                return text
            except Exception:
                ledger.mark_manager_unknown(request["call_id"], "manager_send_outcome_uncertain", generation=generation)
                raise

    def on_action(message: dict[str, Any]) -> dict[str, Any]:
        nonlocal edit_evidence, test_evidence, verifier_input_sha256
        stop_if_cancelled()
        action = _normalized_action(envelope, message)
        is_verifier = action["instance_id"] in job["verifier_instance_ids"] if chartered else action["assignment_id"] == "local-verifier"
        is_producer = action["instance_id"] in job["producer_instance_ids"] if chartered else action["assignment_id"] == "claude-implementer"
        is_evidence_collector = (chartered
                                 and action["instance_id"] in job.get("evidence_collector_instance_ids", []))
        if (chartered and action["provider"] in {"claude", "codex"} and not is_producer
                and not is_evidence_collector
                and not (structured_verifier and is_verifier and action["provider"] == "codex")):
            raise ContractError("selected editor is not eligible to produce this job")
        if (is_evidence_collector or is_verifier) and (edit_evidence is None or test_evidence is None):
            raise ContractError("Magentic read-only specialist selected before Flow verified producer repair")
        with authority_guard():
            decision = ledger.decide(envelope, action, generation=generation)
            regranted = False
            if (recovery is not None and decision.get("replayed") and not decision["allowed"]
                    and decision["reason"] == "recovery_unconsumed_grant"
                    and action["action_id"] in recovery.get("regrantable_action_ids", [])):
                decision = ledger.regrant_recovered_action(envelope, action, generation=generation)
                regranted = decision["allowed"]
            elif (recovery is not None and decision.get("replayed") and not decision["allowed"]
                    and (decision.get("expansion") or {}).get("status") == "granted"):
                # The paused proposal is back under its own identity and keeps
                # the checkpoint bound at the pause; its grant allows it once.
                decision = ledger.regrant_expanded_action(envelope, action, generation=generation)
                regranted = True
        if (decision.get("replayed") and not decision["allowed"]
                and (decision.get("expansion") or {}).get("status") == "denied"):
            # The engineer refused this unit: Magentic hears the denial and continues.
            return denied_reply(action["action_id"], decision["reason"])
        if decision.get("replayed") and isinstance(decision.get("result"), dict):
            return _completed_reply(ledger, envelope, attempt_dir, action, decision["result"],
                                    is_verifier=is_verifier, is_producer=is_producer,
                                    edit_evidence=edit_evidence, test_evidence=test_evidence,
                                    generation=generation, authority_guard=authority_guard)
        paused = _pending_expansion(decision)
        if paused:
            # Bind the denied proposal's checkpoint before stopping, so a
            # decided request can restore this exact position in pending mode.
            with authority_guard():
                checkpoint_path = attempt_dir / "checkpoints" / f"{action['checkpoint_id']}.json"
                if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
                    raise ContractError("Magentic pending-action checkpoint is absent")
                high_water = ledger.snapshot(aid)["events"][-1]["seq"]
                ledger.bind_magentic_checkpoint(aid, action["checkpoint_id"], "worker", action["action_id"],
                                                high_water, str(checkpoint_path), generation=generation)
            raise ExpansionPaused(paused)
        if decision.get("replayed") and not decision["allowed"]:
            raise ContractError("Magentic specialist call needs reconciliation: " + decision["reason"])
        if not decision["allowed"]:
            if structured_verifier and decision["reason"] == "producer_already_completed":
                denied_producer_calls = [
                    item for item in ledger.snapshot(aid)["actions"]
                    if item["status"] == "denied"
                    and item["reason"] == "producer_already_completed"
                    and item["request"]["instance_id"] == action["instance_id"]
                ]
                if len(denied_producer_calls) > 1:
                    # One denial lets the stock manager choose the authorized
                    # verifier retry. Repeating the exhausted editor cannot
                    # change evidence and otherwise drives a denial/replan loop.
                    raise ContractError("structured verifier ended valid_fail; producer repair requires successor attempt")
            if structured_verifier and not decision.get("replayed"):
                # Bind the denied position so a later manager pause can resume
                # from it in answer mode; nothing was granted or sent.
                checkpoint_path = attempt_dir / "checkpoints" / f"{action['checkpoint_id']}.json"
                # Best effort: a restore position must never turn a harmless
                # denial into a failed attempt; without it, recovery refuses.
                if checkpoint_path.is_file() and not checkpoint_path.is_symlink():
                    with suppress(ContractError), authority_guard():
                        high_water = ledger.snapshot(aid)["events"][-1]["seq"]
                        ledger.bind_magentic_checkpoint(aid, action["checkpoint_id"], "worker", action["action_id"],
                                                        high_water, str(checkpoint_path), generation=generation)
            return denied_reply(action["action_id"], decision["reason"])
        provider_action = action
        if is_verifier:
            provider_task = _verifier_provider_task(
                action["task"], (attempt_dir / "repair.diff").read_text(),
                edit_evidence["diff_sha256"], structured=structured_verifier,
                test_output=(test_evidence or {}).get("output_excerpt", ""),
                authority_statement=VERIFIED_HANDOFF_AUTHORITY)
            verifier_input_sha256 = hashlib.sha256(provider_task.encode()).hexdigest()
            provider_action = {**action, "provider_task": provider_task}
        try:
            with authority_guard():
                checkpoint_path = attempt_dir / "checkpoints" / f"{action['checkpoint_id']}.json"
                if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
                    raise ContractError("Magentic pending-action checkpoint is absent")
                if not regranted:
                    # A re-granted proposal keeps the checkpoint it was bound to.
                    high_water = ledger.snapshot(aid)["events"][-1]["seq"]
                    ledger.bind_magentic_checkpoint(aid, action["checkpoint_id"], "worker", action["action_id"],
                                                    high_water, str(checkpoint_path), generation=generation)
                stop_if_cancelled()  # before the grant is used; the except below releases it
                if not (structured_verifier and is_verifier) and not ledger.consume_grant(
                        action["action_id"], decision["grant_id"], generation=generation):
                    raise ContractError("Magentic specialist grant was already consumed")
        except Exception:
            with authority_guard():
                ledger.close_pre_send_failure(action["action_id"], decision["grant_id"], generation=generation)
            raise
        with authority_guard(), ledger.send_lock():
            ledger.assert_owner(aid, generation)
            response_completed = False
            verifier_binding: dict[str, Any] | None = None
            if structured_verifier and is_verifier:
                stop_if_cancelled()  # the verifier grant is still unused here, so the seal releases it
                # Input binding, grant use, and send claim are one ledger
                # transaction. If it refuses, nothing was sent: release an
                # untouched grant rather than leaving it reserved.
                try:
                    verifier_binding = ledger.prepare_verifier_send(
                        action["action_id"], decision["grant_id"], provider_action,
                        edit_evidence["diff_sha256"], test_evidence["output_sha256"],
                        generation=generation)
                except Exception:
                    # Never let the release attempt mask the original refusal.
                    with suppress(Exception):
                        ledger.close_pre_send_failure(action["action_id"], decision["grant_id"], generation=generation)
                    raise
            try:
                if not (structured_verifier and is_verifier):
                    ledger.observe_send(action["action_id"], generation)
                result = worker_adapter(provider_action, envelope=envelope, workspace=worktree)
                if not (structured_verifier and is_verifier):
                    validate_result(envelope, result, action=action)
                ledger.observe_response(action["action_id"], result, generation)
                if chartered:
                    # The provider turn is observed even when later Flow validation
                    # rejects its edit. Preserve that fact instead of claiming an
                    # uncertain provider outcome.
                    ledger.complete(action["action_id"], result, generation=generation)
                    response_completed = True
                    if structured_verifier and is_verifier:
                        evaluation = _evaluate_verifier(ledger, action, result, verifier_binding, generation=generation)
                    if is_evidence_collector:
                        manifest = json.loads((attempt_dir / "manifest.snapshot.json").read_text())
                        assignment = next(item for item in manifest["assignments"] if item["id"] == action["assignment_id"])
                        relative = assignment["output"]["path"]
                        project_root = attempt_dir.parents[4]
                        run_dir = attempt_dir.parents[1]
                        target = project_root / relative
                        if (target.is_symlink() or target.resolve().parent != run_dir.resolve()
                                or Path(relative).name != target.name):
                            raise ContractError("evidence collector output path escapes the run")
                        write_atomic(target, result["output"].rstrip() + "\n", mode=0o600)
                if is_producer:
                    edit_evidence = verify_edit(worktree, baseline, attempt_dir)
                    test_evidence = test_runner(worktree)
                    if chartered and verify_edit(worktree, baseline, attempt_dir) != edit_evidence:
                        raise ContractError("targeted test changed the verified worktree diff")
                if not chartered:
                    ledger.complete(action["action_id"], result, generation=generation)
            except Exception:
                if not response_completed:
                    ledger.mark_unknown(action["action_id"], "specialist_send_outcome_uncertain", generation=generation)
                raise
        summary = result["output"]
        if structured_verifier and is_verifier:
            summary = _verifier_summary(ledger, aid, evaluation, result["output"])
        if is_producer and edit_evidence and test_evidence:
            summary = _producer_summary(summary, edit_evidence, attempt_dir)
        reply = {"status": "completed", "action_id": action["action_id"], "summary": summary, "output": result["output"]}
        reply_path = attempt_dir / f"action-{action['action_id']}.result.json"
        if reply_path.exists():
            if json.loads(reply_path.read_text()) != reply:
                raise ContractError("Magentic action response conflicts with durable replay")
        else:
            _write_snapshot(reply_path, (canonical(reply) + "\n").encode())
        return reply

    paused_request: str | None = None
    try:
        runner_kwargs = {"python_path": python_path, "timeout_s": envelope["limits"].get("max_runtime_seconds", 900)}
        if resume is not None:
            runner_kwargs["resume"] = resume
        if supervisor is None and register is not None:
            runner_kwargs["on_process_group"] = register
        outcome = (supervisor or run_maf_delivery)(envelope, task, on_manager, on_action, **runner_kwargs)
        if outcome.get("attempt_id") != aid:
            raise ContractError("Magentic finished a different attempt")
    except ExpansionPaused as paused:
        paused_request = paused.request_id
    except Exception as exc:
        failure = str(exc)
        failure_exception = exc
        recoverable_transport_failure = isinstance(exc, MafTransportError)
    if controller is not None and controller.requested:
        # Keyed on the flag, not the exception: the stack has unwound, every
        # in-flight send is already unknown, and nothing new is authorized.
        return delivery_termination.stop_on_cancel(envelope, attempt_dir, ledger, generation=generation,
                                                   detail=failure or "cancel requested")
    if paused_request is not None:
        # Not an interruption and not a failure: the attempt stays started,
        # the lead claim keeps its generation, and the pending request row is
        # the durable pause marker. Nothing is in flight, so stopping the
        # child loses nothing.
        return {"attempt_id": aid, "status": "expansion_paused", "request_id": paused_request,
                "receipt_path": None, "resume_available": False,
                "next_action": f"decide expansion {paused_request}"}
    snapshot = ledger.snapshot(aid)
    actions = snapshot["actions"]
    manager_calls = snapshot.get("manager_calls", [])
    uncertain = any(item["status"] in {"started", "unknown"} for item in actions + manager_calls)
    if failure and recoverable_transport_failure and not chartered and not uncertain and any(item["status"] == "completed" for item in actions):
        interruption = {"attempt_id": aid, "status": "interrupted", "reason": failure[:512],
                        "last_completed_action": next(item["action_id"] for item in reversed(actions) if item["status"] == "completed"),
                        "created_at": utc_now()}
        write_atomic(attempt_dir / "interruption.json", canonical(interruption) + "\n", mode=0o600)
        return {"attempt_id": aid, "status": "interrupted", "reason": failure,
                "receipt_path": None, "resume_available": True}
    if structured_verifier and (uncertain or (failure and recoverable_transport_failure)):
        # v8 never seals transport loss or uncertainty. The attempt stays
        # started; an explicit recovery reconciles and continues it.
        cause = "reconciliation_required" if uncertain else "transport"
        with authority_guard(), ledger.send_lock():
            interruption = ledger.record_interruption(aid, cause, failure, generation=generation)
        # A clean transport loss is not necessarily resumable. The latest
        # checkpoint may belong to a denied or otherwise unreplayable action,
        # so report the same ledger-derived verdict used by inspect/recovery.
        recovery = recovery_eligibility(envelope, ledger.snapshot(aid), lead_active=True)
        blocking = [item.get("action_id") or item.get("call_id") for item in actions + manager_calls
                    if item["status"] in {"started", "unknown"}]
        return {"attempt_id": aid, "status": "interrupted", "reason": cause, "detail": failure[:512],
                "interruption_id": interruption["interruption_id"], "receipt_path": None,
                "resume_available": recovery["recoverable"], "blocking": blocking}
    if structured_verifier:
        with authority_guard(), ledger.send_lock():
            ledger.record_runtime_outcome(aid, failure=failure, transport=recoverable_transport_failure,
                                          generation=generation)
        if controller is not None:
            # Committed to sealing: a cancel that arrives now finds the normal receipt.
            controller.disarm()
        hook("after-runtime-outcome")
    if not continuation_epoch_id:
        failure_class = ("maf_runtime_startup" if failure and not actions and not manager_calls
                         and isinstance(failure_exception, (MafProtocolError, MafChildError)) else None)
        return _seal_attempt(envelope, attempt_dir, ledger, snapshot, failure=failure, failure_class=failure_class,
                             edit_evidence=edit_evidence, test_evidence=test_evidence,
                             verifier_input_sha256=verifier_input_sha256, generation=generation,
                             authority_guard=authority_guard, hook=hook)
    receipt, terminal, reason = _build_receipt(envelope, attempt_dir, ledger, snapshot, failure=failure,
                                               edit_evidence=edit_evidence, test_evidence=test_evidence,
                                               verifier_input_sha256=verifier_input_sha256,
                                               continuation_epoch_id=continuation_epoch_id)
    validate_receipt(envelope, receipt)
    receipt_path = attempt_dir / f"continuation-{continuation_epoch_id}.receipt.json"
    with authority_guard(), ledger.send_lock():
        ledger.assert_owner(aid, generation)
        _write_snapshot(receipt_path, (canonical(receipt) + "\n").encode())
        ledger.finish_magentic_continuation(continuation_epoch_id, terminal, reason,
                                            str(receipt_path), generation=generation)
    return {"attempt_id": aid, "status": terminal, "reason": reason, "receipt_path": str(receipt_path),
            "evidence": receipt["evidence"]}


def _seal_attempt(envelope: dict[str, Any], attempt_dir: Path, ledger: ExecutionLedger, snapshot: dict[str, Any], *,
                  failure: str, failure_class: str | None = None, edit_evidence: dict[str, Any] | None, test_evidence: dict[str, Any] | None,
                  verifier_input_sha256: str | None, generation: int, authority_guard: Callable[[], Any],
                  hook: Callable[[str], None]) -> dict[str, Any]:
    """Build, validate, write, and seal an attempt receipt under the owner fence."""
    aid = envelope["attempt_id"]
    receipt_path = attempt_dir / "receipt.json"
    if envelope["execution_protocol_version"] != 8:
        receipt, terminal, reason = _build_receipt(envelope, attempt_dir, ledger, snapshot, failure=failure,
                                                   edit_evidence=edit_evidence, test_evidence=test_evidence,
                                                   verifier_input_sha256=verifier_input_sha256,
                                                   continuation_epoch_id=None)
        if failure_class is not None:
            receipt["failure_class"] = failure_class
        validate_receipt(envelope, receipt)
        hook("after-receipt-draft")
        with authority_guard(), ledger.send_lock():
            ledger.assert_owner(aid, generation)
            write_atomic(receipt_path, canonical(receipt) + "\n", mode=0o600)
            hook("before-finish-attempt")
            ledger.finish_attempt(aid, terminal, reason, str(receipt_path), generation=generation)
        return {"attempt_id": aid, "status": terminal, "reason": reason, "receipt_path": str(receipt_path),
                "evidence": receipt["evidence"]}
    # v8: one send_lock hold closes expansions, snapshots, builds and seals, so
    # the receipt rows are the rows finish_attempt compares (ADR 0020).
    if not handback_supported(envelope):
        # Refused before any draft is written; abandon is the only way to end it.
        raise ContractError("attempt predates the sealed token budget; abandon it")
    with authority_guard(), ledger.send_lock():
        # A sealed attempt keeps no open request or unused grant.
        ledger.close_expansions(aid, "sealed", generation=generation)
        view = ledger.seal_view(aid)
        receipt, terminal, reason = _build_receipt(envelope, attempt_dir, ledger, view["snapshot"], failure=failure,
                                                   edit_evidence=edit_evidence, test_evidence=test_evidence,
                                                   verifier_input_sha256=verifier_input_sha256,
                                                   continuation_epoch_id=None, blocks=view["blocks"])
        if failure_class is not None:
            receipt["failure_class"] = failure_class
        validate_receipt(envelope, receipt)
        hook("after-receipt-draft")
        ledger.assert_owner(aid, generation)
        write_atomic(receipt_path, canonical(receipt) + "\n", mode=0o600)
        hook("before-finish-attempt")
        ledger.finish_attempt(aid, terminal, reason, str(receipt_path), generation=generation,
                              failure_class=failure_class)
    return {"attempt_id": aid, "status": terminal, "reason": reason, "receipt_path": str(receipt_path),
            "evidence": receipt["evidence"]}


def _default_manager_adapter(message: dict[str, Any], *, envelope: dict[str, Any], workspace: Path,
                             on_process_group: Callable[..., None] | None = None) -> dict[str, Any]:
    prompt = render_manager_prompt(message["messages"])
    if on_process_group is not None and isinstance(message.get("call_id"), str):
        on_process_group = partial(on_process_group, row_id=message["call_id"])
    timeout_seconds = min(120, envelope.get("limits", {}).get("max_runtime_seconds", 120))
    if envelope["manager"].get("provider", "claude") == "claude":
        result = call_claude(instructions="stock Magentic manager", task="model response",
                             prompt_override=prompt, workspace=workspace,
                             model=envelope["manager"]["model"], timeout_seconds=timeout_seconds,
                             max_output_bytes=32768, on_process_group=on_process_group)
    elif envelope["manager"]["provider"] == "codex":
        result = call_codex(instructions="Respond to the stock Magentic manager request only. Return the requested response text without editing files.",
                            task=prompt, workspace=workspace, model=envelope["manager"]["model"],
                            timeout_seconds=timeout_seconds, sandbox="read-only",
                            max_prompt_bytes=MAX_MANAGER_MESSAGES_BYTES,
                            max_output_bytes=32768, on_process_group=on_process_group)
    else:
        raise ContractError("approved manager provider has no adapter")
    output = result["output"]
    if output.startswith("```json\n") and output.rstrip().endswith("```"):
        inner = output.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(inner)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(parsed, dict) and {"is_request_satisfied", "next_speaker"} <= set(parsed):
                result = {**result, "output": inner, "normalization": "exact_json_fence",
                          "raw_output_sha256": result["output_sha256"]}
    return result


def _default_worker_adapter(action: dict[str, Any], *, envelope: dict[str, Any], workspace: Path,
                            trace_dir: Path | None = None,
                            on_process_group: Callable[..., None] | None = None) -> dict[str, Any]:
    assignment = next(item for item in envelope["roster"] if item["assignment_id"] == action["assignment_id"])
    if on_process_group is not None and isinstance(action.get("action_id"), str):
        on_process_group = partial(on_process_group, row_id=action["action_id"])
    # Hosted provider workers support up to 600 seconds. Ollama is local and
    # user-owned, so it has no elapsed-time deadline; explicit cancellation
    # remains available through the interruptible transport.
    timeout_seconds = min(600, envelope.get("limits", {}).get("max_runtime_seconds", 600))
    if action["provider"] == "ollama":
        structured = (envelope["execution_protocol_version"] == 8
                      and action["instance_id"] in envelope["job_contract"]["verifier_instance_ids"])
        # A verifier's sealed role body keeps its digest; Flow derives the sent
        # system instructions so its own output contract is the only format.
        instructions = verifier_instructions(assignment["instructions"]) if structured else assignment["instructions"]
        return call_local({**assignment, "instructions": instructions,
                           "task": action.get("provider_task", action["task"]), "attempt_id": envelope["attempt_id"]},
                          correlation_id=action["action_id"], timeout_seconds=None,
                          structured_verifier=structured)
    if action["provider"] == "claude":
        return call_claude_edit(instructions=assignment["instructions"], task=action["task"],
                                workspace=workspace, model=assignment["model"], timeout_seconds=timeout_seconds,
                                trace_path=(trace_dir / "claude-implementer.debug.log") if trace_dir else None,
                                on_process_group=on_process_group)
    if action["provider"] == "codex" and envelope["execution_protocol_version"] in {6, 7, 8}:
        is_verifier = (envelope["execution_protocol_version"] == 8
                       and action["instance_id"] in envelope["job_contract"]["verifier_instance_ids"])
        is_evidence_collector = (envelope["execution_protocol_version"] == 8
                                 and action["instance_id"] in envelope["job_contract"].get(
                                     "evidence_collector_instance_ids", []))
        return call_codex(instructions=assignment["instructions"],
                          task=action.get("provider_task", action["task"]),
                          workspace=workspace, model=assignment["model"], timeout_seconds=timeout_seconds,
                          sandbox="read-only" if is_verifier or is_evidence_collector else "workspace-write",
                          on_process_group=on_process_group)
    raise ContractError("selected specialist provider has no approved adapter")


def execute_v9_selected_action(envelope: dict[str, Any], action: dict[str, Any],
                               adapter_send: Callable[[dict[str, Any], dict[str, Any]], Any], *,
                               readiness_recheck: Callable[[dict[str, Any]], dict[str, Any]],
                               ledger: ExecutionLedger | None = None,
                               generation: int | None = None,
                               predecessor_selection_id: str | None = None) -> dict[str, Any]:
    """Execute one v9 provider action through Flow's durable send fence.

    The caller is responsible for constructing the sealed v9 envelope and
    logical action.  Once an ``ExecutionLedger`` is supplied this is a live
    adapter boundary: selection reservation, provider-send claim, and result
    closure are ledger-owned.  Existing v8 dispatch never reaches this path.
    """
    return authorize_v9_and_dispatch(
        envelope, action, adapter_send, readiness_recheck=readiness_recheck,
        ledger=ledger, generation=generation,
        predecessor_selection_id=predecessor_selection_id,
    )


def execute_v9_logical_delivery(envelope: dict[str, Any], task: str, ledger: ExecutionLedger,
                                adapter_send: Callable[[dict[str, Any], dict[str, Any]], Any], *,
                                readiness_recheck: Callable[[dict[str, Any]], dict[str, Any]],
                                supervisor: Callable[..., dict[str, Any]] | None = None,
                                python_path: str | None = None) -> dict[str, Any]:
    """Run a sealed v9 logical assignment through MAF, Flow, and one adapter.

    MAF proposes only the logical assignment/task.  Flow creates the action,
    recomputes the sealed binding, owns reservation and send claim, then calls
    the selected adapter.  No MAF process receives provider credentials or a
    concrete model/provider route.
    """
    if envelope.get("execution_protocol_version") != 9:
        raise ContractError("logical v9 delivery requires a protocol v9 envelope")
    snapshot = ledger.snapshot(envelope["attempt_id"])
    if snapshot["envelope"] != envelope or snapshot["status"] != "started":
        raise ContractError("logical v9 delivery attempt is absent or closed")
    generation = snapshot["owner_generation"]
    with delivery_authority_guard(Path(envelope["checkpoint_dir"]).parents[2], envelope):
        pass
    attempt_dir = Path(envelope["checkpoint_dir"]).parent
    live_attempt = (attempt_dir.is_absolute() and attempt_dir.is_dir() and not attempt_dir.is_symlink()
                    and (attempt_dir / "job-charter.snapshot.json").is_file()
                    and (attempt_dir / "baseline.json").is_file())
    job: dict[str, Any] | None = None
    baseline: dict[str, Any] | None = None
    edit_evidence: dict[str, Any] | None = None
    test_evidence: dict[str, Any] | None = None
    verifier_evaluations: dict[str, dict[str, Any]] = {}
    if live_attempt:
        job = json.loads((attempt_dir / "job-charter.snapshot.json").read_text())
        baseline = json.loads((attempt_dir / "baseline.json").read_text())
    dispatch_sequence_base = max((a["request"]["sequence"] for a in snapshot["actions"]), default=0) + 1

    class ProviderCandidatesExhausted(Exception):
        def __init__(self, result: dict[str, Any]) -> None:
            self.result = result

    def dispatch(proposal: dict[str, Any]) -> dict[str, Any]:
        nonlocal dispatch_sequence_base
        assignment = next((item for item in envelope["logical_assignments"]
                           if item["assignment_id"] == proposal["assignment_id"]), None)
        if assignment is None:
            raise ContractError("logical v9 proposal names an unknown assignment")
        sequence = dispatch_sequence_base
        if sequence > envelope["limits"]["max_actions"]:
            raise ContractError("sealed v9 action budget exhausted; approval is required for more work")
        runtime_families = (_runtime_family_exclusions(envelope, proposal["assignment_id"], ledger)
                            if assignment["requirements"]["operation"] == "verify" else None)
        action = make_v9_action(
            envelope, proposal["assignment_id"], proposal["task"],
            sequence=sequence, manager_turn=proposal["manager_turn"],
            runtime_excluded_families=runtime_families,
        )
        orphan_chains = [row for row in snapshot.get("provider_selections", [])
                         if row["decision"]["requirements_digest"] == action["selection_decision"]["requirements_digest"]
                         and row["logical_action_id"] not in {
                             r["request"]["logical_action_id"] for r in snapshot["actions"]
                             if r["status"] == "completed"}]
        if orphan_chains:
            if len({row["logical_action_id"] for row in orphan_chains}) != 1:
                raise ContractError("ambiguous unfinished logical selection chains require explicit recovery")
            logical_id = orphan_chains[0]["logical_action_id"]
            journal = attempt_dir / ("logical-action-" + logical_id + ".json")
            if journal.is_file() and not journal.is_symlink():
                saved = json.loads(journal.read_text())
            elif refused_actions := [row["request"] for row in snapshot["actions"]
                                     if row["request"]["logical_action_id"] == logical_id
                                     and row["status"] == "observed_not_executed"]:
                # The durable refusal retains the exact task/sequence even
                # for embedding callers that have no action journal.
                original = refused_actions[0]
                saved = make_v9_action(envelope, proposal["assignment_id"], original["task"],
                                       sequence=original["sequence"], manager_turn=original["manager_turn"],
                                       decision=orphan_chains[0]["decision"])
            else:
                # Historical relay jobs did not persist a logical proposal.
                # Recover only the deterministic task reconstructed from their
                # sealed charter and final observed manager decision.
                prior_manager = snapshot["actions"][-1]["request"]
                legacy_task = (f"Approved job:\n{task.strip()}\n\n"
                               f"Logical assignment: {proposal['assignment_id']}\n"
                               f"Sealed instructions:\n{assignment['instructions'].strip()}")
                saved = make_v9_action(envelope, proposal["assignment_id"], legacy_task,
                                       sequence=prior_manager["sequence"] + 1,
                                       manager_turn=prior_manager["manager_turn"] + 1,
                                       runtime_excluded_families=runtime_families)
            if saved["logical_action_id"] != logical_id or saved["assignment_id"] != proposal["assignment_id"]:
                raise ContractError("persisted unsent logical action requires explicit recovery")
            action = saved
            proposal = {**proposal, "task": saved["task"], "manager_turn": saved["manager_turn"]}
            sequence = saved["sequence"]
        if live_attempt:
            write_atomic(attempt_dir / ("logical-action-" + action["logical_action_id"] + ".json"),
                         canonical(action) + "\n", mode=0o600)
        predecessor_selection_id = None
        terminal_refused_action = None
        # A process can stop after Flow durably records a positive no-send
        # refusal but before it reserves the deterministic successor. Resume
        # that exact chain instead of trying to reserve the refused decision
        # again. A computed/reserved tail is also safe to re-enter because no
        # provider action (and therefore no send claim) exists for it.
        prior_chain = [item for item in snapshot.get("provider_selections", [])
                       if item["logical_action_id"] == action["logical_action_id"]]
        for index, row in enumerate(prior_chain):
            if (row["selection_id"] != action["selection_id"]
                    or row["decision"] != action["selection_decision"]
                    or row["predecessor_selection_id"] != predecessor_selection_id):
                raise ContractError("logical v9 persisted selection chain differs from deterministic replay")
            last = index == len(prior_chain) - 1
            if row["state"] in {"computed", "reserved"}:
                if not last:
                    raise ContractError("logical v9 persisted selection chain has an open interior decision")
                predecessor_selection_id = row["predecessor_selection_id"]
                break
            if row["state"] not in {"superseded", "pre_send_refused", "observed_not_executed"}:
                raise ContractError("logical v9 persisted selection chain is not safely resumable")
            if not last and row["state"] == "pre_send_refused":
                raise ContractError("logical v9 persisted selection chain has an unsuperseded interior refusal")
            if last and row["state"] == "superseded":
                raise ContractError("logical v9 persisted selection chain has no resumable tail")
            if last and row["state"] == "pre_send_refused":
                terminal_refused_action = action
            prior_no_send = list(row["decision"].get("prior_no_send_failures", []))
            prior_retryable = list(row["decision"].get("prior_retryable_failures", []))
            if row["state"] in {"superseded", "pre_send_refused"}:
                prior_no_send.append(row["candidate_id"])
            else:
                prior_retryable.append(row["candidate_id"])
            successor = compute_v9_binding(
                envelope, proposal["assignment_id"],
                prior_no_send_failures=prior_no_send,
                prior_retryable_failures=prior_retryable,
                runtime_excluded_families=runtime_families,
            )
            predecessor_selection_id = row["selection_id"]
            action = make_v9_action(
                envelope, proposal["assignment_id"], proposal["task"],
                sequence=sequence, manager_turn=proposal["manager_turn"],
                decision=successor,
            )
        if prior_chain and action["selection_decision"].get("selected_binding") is None:
            if live_attempt:
                if terminal_refused_action is None:
                    raise ContractError("logical v9 exhausted selection has no terminal refusal")
                ledger.record_v9_terminal_pre_send_action(
                    envelope, terminal_refused_action, generation=generation)
                sealed = ledger.seal_v9_attempt(
                    envelope["attempt_id"], "failed", "provider_candidates_exhausted",
                    attempt_dir / "receipt.json", generation=generation)
                raise ProviderCandidatesExhausted({
                    "attempt_id": envelope["attempt_id"], "status": "failed",
                    "reason": "provider_candidates_exhausted", **sealed,
                })
            return {"status": "failed", "reason": "provider_candidates_exhausted",
                    "selection_id": predecessor_selection_id}
        # A refused readiness check is the sole automatic retry case: it is
        # positively evidenced to have happened before provider I/O.  Every
        # adapter failure after a send claim becomes recovery-required instead.
        while True:
            run_dir = Path(envelope["checkpoint_dir"]).parents[2]
            with delivery_authority_guard(run_dir, envelope):
                result = execute_v9_selected_action(
                    envelope, action, adapter_send, readiness_recheck=readiness_recheck,
                    ledger=ledger, generation=generation,
                    predecessor_selection_id=predecessor_selection_id,
                )
            if result["status"] not in {"pre_send_refused", "observed_not_executed"}:
                break
            successor = result["successor_decision"]
            if successor.get("selected_binding") is None:
                if live_attempt:
                    ledger.record_v9_terminal_pre_send_action(
                        envelope, action, generation=generation)
                    sealed = ledger.seal_v9_attempt(
                        envelope["attempt_id"], "failed", "provider_candidates_exhausted",
                        attempt_dir / "receipt.json", generation=generation)
                    raise ProviderCandidatesExhausted({
                        "attempt_id": envelope["attempt_id"], "status": "failed",
                        "reason": "provider_candidates_exhausted", **sealed,
                    })
                return {"status": "failed", "reason": "provider_candidates_exhausted",
                        "selection_id": action["selection_id"]}
            predecessor_selection_id = action["selection_id"]
            action = make_v9_action(
                envelope, proposal["assignment_id"], proposal["task"],
                sequence=sequence, manager_turn=proposal["manager_turn"],
                decision=successor,
            )
        # The child only needs Flow's outcome. The complete binding/action
        # remains in the ledger and receipt, rather than echoing it back.
        response = {"status": result["status"], "provider_action_id": action["action_id"],
                    "selection_id": action["selection_id"]}
        if assignment["requirements"]["operation"] == "manage":
            response["manager_result"] = result.get("result")
        # Resuming a refusal reuses its original sequence; it must not spend
        # an additional sequence slot after the new coordination call.
        dispatch_sequence_base = max(dispatch_sequence_base, sequence + 1)
        return response

    managers = [item for item in envelope["logical_assignments"]
                if item["requirements"].get("operation") == "manage"]
    if len(managers) != 1:
        raise ContractError("protocol v9 requires exactly one logical manager assignment")
    manager = managers[0]
    workers = [item for item in envelope["logical_assignments"]
               if item["requirements"].get("operation") != "manage"]
    if not workers:
        raise ContractError("protocol v9 requires at least one logical worker assignment")
    pending = {item["assignment_id"]: item for item in workers}
    completed: set[str] = set()
    prior_actions = snapshot["actions"]
    if any(item["status"] not in {"completed", "observed_not_executed"} for item in prior_actions):
        raise ContractError("logical v9 continuation requires reconciliation of every uncertain send")
    failed_action_ids = {item["action_id"] for item in snapshot.get("events", [])
                         if item["event"] == "v9_evidence_failed"}
    for item in prior_actions:
        if item["status"] != "completed":
            continue
        assignment_id = item["request"]["assignment_id"]
        if assignment_id in pending:
            if item["action_id"] in failed_action_ids:
                completed.discard(assignment_id)
            else:
                completed.add(assignment_id)
    for assignment_id in completed:
        pending.pop(assignment_id, None)
    if live_attempt and completed:
        completed_assignments = {item["assignment_id"]: item for item in workers
                                 if item["assignment_id"] in completed}
        if any(item["requirements"]["operation"] == "edit"
               for item in completed_assignments.values()):
            if job is None or baseline is None:
                raise ContractError("logical v9 continuation evidence contract is absent")
            edit_evidence = _verify_chartered_edit(Path(envelope["worktree"]), baseline, attempt_dir, job)
            test_evidence = _run_chartered_test(Path(envelope["worktree"]), job)
            if _verify_chartered_edit(Path(envelope["worktree"]), baseline, attempt_dir, job) != edit_evidence:
                raise ContractError("chartered test changed the resumed v9 worktree diff")
    action_by_id = {item["request"]["action_id"]: item["request"] for item in prior_actions}
    for evaluation in snapshot.get("verifier_evaluations", []):
        action = action_by_id.get(evaluation.get("action_id"))
        if action is not None:
            verifier_evaluations[action["assignment_id"]] = evaluation["evaluation"]

    selected_proposal: tuple[str, str, int] | None = None

    def frontier_ids() -> list[str]:
        return sorted(item["assignment_id"] for item in pending.values()
                      if set(item.get("depends_on", [])) <= completed)

    def on_manager(message: dict[str, Any]) -> str:
        nonlocal dispatch_sequence_base, selected_proposal
        serialized = message.get("messages")
        phase = message.get("phase")
        if (phase not in {"facts", "plan", "progress", "replan_facts", "replan_plan", "final"}
                or not isinstance(serialized, list)
                or hashlib.sha256(canonical(serialized).encode()).hexdigest() != message.get("prompt_digest")):
            raise ContractError("invalid stock Magentic manager request")
        allowed_ids = frontier_ids()
        prompt = canonical(serialized)
        prompt += "\nFlow accepted assignments: " + json.dumps(sorted(completed))
        if phase == "progress":
            prompt += ("\nnext_speaker.answer must be exactly one of " + json.dumps(allowed_ids or sorted(completed))
                       + ".\nSet is_request_satisfied.answer=false while required assignments remain."
                       + " Flow permitted unfinished frontier: " + json.dumps(allowed_ids))
        if len(prompt.encode()) > manager["requirements"]["input_bytes"]:
            raise ContractError("stock manager prompt exceeds sealed input budget")
        result = dispatch({"assignment_id": manager["assignment_id"], "task": prompt,
                           "manager_turn": message["sequence"]})
        raw = result.get("manager_result")
        text = raw.get("output") if isinstance(raw, dict) else None
        progress = raw.get("manager_response") if isinstance(raw, dict) else None
        if phase == "progress":
            if progress is None and isinstance(text, str):
                progress = parse_progress(text).value
            if not isinstance(progress, dict):
                # Stock Magentic owns the bounded parse retry, through a new
                # authorized manager call; no worker send is retried here.
                return text if isinstance(text, str) else "invalid progress"
            selected = progress.get("next_speaker", {}).get("answer")
            reason = progress.get("next_speaker", {}).get("reason")
            instruction = progress.get("instruction_or_question", {}).get("answer")
            satisfied = progress.get("is_request_satisfied", {}).get("answer")
            if (type(satisfied) is not bool or not isinstance(reason, str) or not reason.strip()
                    or len(reason.encode()) > MAX_TASK_BYTES or satisfied and pending
                    or not satisfied and selected not in allowed_ids
                    or not isinstance(instruction, str) or not instruction.strip()
                    or len(instruction.encode()) > MAX_TASK_BYTES):
                raise ContractError("Magentic decision is outside the permitted frontier or completion gate")
            selected_proposal = (selected, instruction, message["sequence"])
            return canonical(progress)
        if not isinstance(text, str) or not text.strip():
            raise ContractError("stock manager phase returned no text")
        return text

    def on_worker(proposal: dict[str, Any]) -> dict[str, Any]:
        nonlocal dispatch_sequence_base, edit_evidence, test_evidence
        selected = proposal.get("assignment_id")
        if (selected_proposal != (selected, proposal.get("task"), proposal.get("manager_turn"))
                or selected not in frontier_ids()):
            raise ContractError("worker proposal differs from the permitted Magentic decision")
        selected_assignment = pending[selected]
        if proposal.get("checkpoint_id") is not None:
            checkpoint = Path(envelope["checkpoint_dir"]) / (proposal["checkpoint_id"] + ".json")
            if (checkpoint.resolve().parent != Path(envelope["checkpoint_dir"]).resolve()
                    or not checkpoint.is_file() or checkpoint.is_symlink() or checkpoint.stat().st_size > 1024 * 1024):
                raise ContractError("Magentic proposal checkpoint is absent")
            write_atomic(attempt_dir / ("coordination-" + str(dispatch_sequence_base) + ".json"),
                         canonical({"proposal": proposal, "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                                    "owner_generation": generation}) + "\n", mode=0o600)
        bounded_task = (f"Approved job:\n{task.strip()}\n\n"
                        f"Logical assignment: {selected}\n"
                        f"Sealed instructions:\n{selected_assignment['instructions'].strip()}\n"
                        f"Magentic instruction:\n{proposal['task']}")
        latest_failures = [event for event in ledger.snapshot(envelope["attempt_id"])["events"]
                           if event["event"] == "v9_evidence_failed"
                           and event["action_id"] in {row["action_id"] for row in ledger.snapshot(envelope["attempt_id"])["actions"]
                                                     if row["request"]["assignment_id"] == selected}]
        if latest_failures:
            bounded_task += "\nFlow validation feedback: " + json.loads(latest_failures[-1]["detail"])["detail"]
        operation = selected_assignment["requirements"]["operation"]
        if len(bounded_task.encode()) > MAX_TASK_BYTES:
            raise ContractError("logical v9 sealed assignment task exceeds size limit")
        if live_attempt and operation == "verify":
            if edit_evidence is None or test_evidence is None:
                raise ContractError("logical v9 verifier selected before Flow captured edit and test evidence")
            bounded_task = verifier_provider_task(
                bounded_task, (attempt_dir / "repair.diff").read_text(),
                edit_evidence["diff_sha256"], structured=True,
                test_output=test_evidence["output_excerpt"],
                authority_statement=VERIFIED_HANDOFF_AUTHORITY,
            )
        input_limit = selected_assignment["requirements"]["input_bytes"]
        if len(bounded_task.encode()) > input_limit:
            raise ContractError("logical v9 evidence-bearing task exceeds assignment input limit")
        result = dispatch({**proposal, "task": bounded_task})
        if live_attempt and operation == "edit":
            if job is None or baseline is None:
                raise ContractError("logical v9 job evidence contract is absent")
            worker_action = next(item["request"] for item in reversed(
                ledger.snapshot(envelope["attempt_id"])["actions"])
                if item["request"]["assignment_id"] == selected)
            try:
                edit_evidence = _verify_chartered_edit(Path(envelope["worktree"]), baseline, attempt_dir, job)
            except ContractError as exc:
                ledger.record_v9_evidence_failure(envelope["attempt_id"], worker_action["action_id"],
                                                  "edit_scope", str(exc), generation=generation)
                sealed = ledger.seal_v9_attempt(
                    envelope["attempt_id"], "failed", "edit_scope_validation_failed",
                    attempt_dir / "receipt.json", generation=generation)
                raise ProviderCandidatesExhausted({"attempt_id": envelope["attempt_id"], "status": "failed",
                        "reason": "edit_scope_validation_failed", **sealed})
            try:
                test_evidence = _run_chartered_test(Path(envelope["worktree"]), job)
                if _verify_chartered_edit(Path(envelope["worktree"]), baseline, attempt_dir, job) != edit_evidence:
                    raise ContractError("chartered test changed the verified v9 worktree diff")
            except ContractError as exc:
                ledger.record_v9_evidence_failure(envelope["attempt_id"], worker_action["action_id"],
                                                  "chartered_test", str(exc), generation=generation)
                # Flow denies acceptance; Magentic chooses whether to repair
                # or replan within its bounded loop. The failed assignment
                # remains on the independently computed frontier.
                failures = [row for row in ledger.snapshot(envelope["attempt_id"])["events"]
                            if row["event"] == "v9_evidence_failed"
                            and json.loads(row["detail"])["stage"] == "chartered_test"]
                if len(failures) >= 2:
                    sealed = ledger.seal_v9_attempt(envelope["attempt_id"], "failed", "chartered_test_failed",
                                                    attempt_dir / "receipt.json", generation=generation)
                    raise ProviderCandidatesExhausted({"attempt_id": envelope["attempt_id"], "status": "failed",
                                                       "reason": "chartered_test_failed", **sealed})
                failed_diff = attempt_dir / "repair.diff"
                if failed_diff.is_file() and not failed_diff.is_symlink():
                    os.replace(failed_diff, attempt_dir / "repair-failed-turn-1.diff")
                edit_evidence = None
                test_evidence = None
                return {"status": "validation_failed", "summary": str(exc)[:512]}
        if live_attempt and operation == "verify":
            verifier_action = next(item["request"] for item in reversed(
                ledger.snapshot(envelope["attempt_id"])["actions"])
                if item["request"]["assignment_id"] == selected)
            try:
                raw_result = None
                if raw_result is None:
                    action_rows = ledger.snapshot(envelope["attempt_id"])["actions"]
                    row = next((item for item in reversed(action_rows)
                                if item["request"]["assignment_id"] == selected), None)
                    wrapped = row.get("result") if isinstance(row, dict) else None
                    raw_result = wrapped.get("result") if isinstance(wrapped, dict) else None
                output = raw_result.get("output") if isinstance(raw_result, dict) else None
                if not isinstance(output, str):
                    raise ContractError("logical v9 verifier returned no bounded output")
                verifier_input = {"provider_task": verifier_action["task"], "assignment_id": selected}
                input_digest = hashlib.sha256(canonical(verifier_input).encode()).hexdigest()
                final_evaluation = evaluate_candidate(
                    action_id=verifier_action["action_id"], verifier_input_digest=input_digest,
                    raw_output=output, diff_digest=edit_evidence["diff_sha256"],
                    test_evidence_digest=test_evidence["output_sha256"],
                )
                ledger.record_v9_verifier_evaluation(
                    verifier_action["action_id"], verifier_input, raw_result, final_evaluation,
                    edit_evidence["diff_sha256"], test_evidence["output_sha256"],
                    generation=generation,
                )
                verifier_evaluations[selected] = final_evaluation
            except ContractError as exc:
                ledger.record_v9_evidence_failure(envelope["attempt_id"], verifier_action["action_id"],
                                                  "verifier_evaluation", str(exc), generation=generation)
                sealed = ledger.seal_v9_attempt(
                    envelope["attempt_id"], "failed", "verifier_evaluation_failed",
                    attempt_dir / "receipt.json", generation=generation)
                raise ProviderCandidatesExhausted({"attempt_id": envelope["attempt_id"], "status": "failed",
                        "reason": "verifier_evaluation_failed", **sealed})
        completed.add(selected)
        pending.pop(selected)
        row = ledger.snapshot(envelope["attempt_id"])["actions"][-1]
        wrapped = row.get("result")
        raw = wrapped.get("result") if isinstance(wrapped, dict) else None
        output = raw.get("output") if isinstance(raw, dict) else None
        summary = "Flow observed assignment " + selected
        if isinstance(output, str):
            summary += ": " + output[:4096]
        if operation == "verify" and selected in verifier_evaluations:
            summary += "\nIndependent verification: " + verifier_evaluations[selected]["disposition"]
        return {**result, "summary": summary}

    try:
        outcome = (supervisor or run_maf_v9_delivery)(
            envelope, task, on_worker, on_manager=on_manager,
            completed_assignments=sorted(completed), python_path=python_path,
            coordination_epoch=dispatch_sequence_base)
    except ProviderCandidatesExhausted as exhausted:
        return exhausted.result
    except (ContractError, MafChildError) as exc:
        # A deterministic policy/runtime refusal is a failed attempt only when
        # every send is observed. Transport loss and unknown sends remain in
        # recovery and must not be relabeled as safe retries.
        current = ledger.snapshot(envelope["attempt_id"])
        if not live_attempt or any(row["status"] != "completed" for row in current["actions"]):
            raise
        manager_rows = [row for row in current["actions"]
                        if row["request"]["assignment_id"] == manager["assignment_id"]]
        if not manager_rows:
            raise
        ledger.record_v9_evidence_failure(envelope["attempt_id"], manager_rows[-1]["action_id"],
                                          "manager_evaluation", str(exc)[:512], generation=generation)
        with delivery_authority_guard(Path(envelope["checkpoint_dir"]).parents[2], envelope):
            sealed = ledger.seal_v9_attempt(envelope["attempt_id"], "failed", "manager_evaluation_failed",
                                            attempt_dir / "receipt.json", generation=generation)
        return {"attempt_id": envelope["attempt_id"], "status": "failed",
                "reason": "manager_evaluation_failed", **sealed}
    if pending:
        raise ContractError("Magentic completion proposal lacks required assignment evidence")
    # Seal the receipt only after every dependency-valid logical assignment
    # completed. The ledger remains the source of truth; uncertain sends
    # refuse here and remain in explicit recovery instead.
    if not live_attempt:
        # Pure embedding callers can exercise the MAF/Flow adapter boundary
        # with an in-memory-style ledger fixture. A charter-prepared live
        # attempt always has this private absolute directory and is sealed.
        return outcome
    required_verifiers = {item["assignment_id"] for item in workers
                          if item["requirements"].get("operation") == "verify"}
    all_verifiers_passed = (set(verifier_evaluations) == required_verifiers
                            and all(item["disposition"] == "valid_pass"
                                    for item in verifier_evaluations.values()))
    terminal_status = "completed" if required_verifiers and all_verifiers_passed else "failed"
    failed_dispositions = sorted({item["disposition"] for item in verifier_evaluations.values()
                                  if item["disposition"] != "valid_pass"})
    terminal_reason = ("semantic_verifier_valid_pass" if terminal_status == "completed" else
                       "semantic_verifier_" + (failed_dispositions[0] if failed_dispositions else "missing"))
    with delivery_authority_guard(Path(envelope["checkpoint_dir"]).parents[2], envelope):
        # Recheck retained evidence after the manager's completion proposal.
        if terminal_status == "completed":
            if _verify_chartered_edit(Path(envelope["worktree"]), baseline, attempt_dir, job) != edit_evidence:
                raise ContractError("final retained diff differs from independent verifier evidence")
        sealed = ledger.seal_v9_attempt(envelope["attempt_id"], terminal_status, terminal_reason,
                                        attempt_dir / "receipt.json", generation=generation)
    return {**outcome, "attempt_id": envelope["attempt_id"], "status": terminal_status,
            "reason": terminal_reason, "receipt_path": sealed["receipt_path"],
            "sealed_receipt_sha256": sealed["sealed_receipt_sha256"]}


def prepare_v9_chartered_delivery(work_id: str, worktree: Path, source_commit: str, *,
                                  logical_assignments: list[dict[str, Any]],
                                  catalog: list[dict[str, Any]], availability: list[dict[str, Any]],
                                  framework_policy: dict[str, Any] | None = None,
                                  administrator_policy: dict[str, Any] | None = None,
                                  project_policy: dict[str, Any] | None = None,
                                  run_policy: dict[str, Any] | None = None,
                                  effective_policy: dict[str, Any] | None = None,
                                  independence_constraints: list[dict[str, Any]] | None = None,
                                  root: Path | None = None) -> tuple[dict[str, Any], str, Path, ExecutionLedger]:
    """Prepare a sealed, provider-neutral v9 charter attempt.

    Inputs are Flow configuration/probe DTOs, never a Shaper-selected provider
    roster.  They are closed and sealed by ``validate_envelope`` before the
    attempt is created. The old v8 preparer remains a separate entry point.
    """
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    state = run_status(work_id, root=project_root)
    if state.get("state") != "implementing" or state.get("protocol_revision") != 2:
        raise ContractError("v9 delivery requires an implementing revision-2 run")
    delivery = state.get("delivery")
    authority = _sealed_delivery_authority(run_dir, delivery)
    valid, _, findings = validate_orchestration(work_id, "dispatch", root=project_root)
    if not valid:
        raise ContractError("orchestration dispatch invalid: " + "; ".join(f.message for f in findings))
    artifacts = state.get("artifacts", {})
    requirements = _run_file(project_root, run_dir, artifacts.get("requirements", ""))
    acceptance = _run_file(project_root, run_dir, artifacts.get("acceptance_criteria", ""))
    manifest = _run_file(project_root, run_dir, artifacts.get("orchestration_manifest", ""))
    charter = _run_file(project_root, run_dir, artifacts.get("job_charter", ""))
    approved_charter_digest = (state.get("approved_artifact_digests") or {}).get("job_charter")
    if (state.get("job_charter_migrations") and (not isinstance(approved_charter_digest, str)
            or hashlib.sha256(charter.read_bytes()).hexdigest() != approved_charter_digest)):
        raise ContractError("approved v9 job charter digest is absent or stale")
    task = json.loads(charter.read_text()).get("task") if charter.suffix == ".json" else charter.read_text()
    if not isinstance(task, str) or not task.strip() or len(task.encode()) > MAX_TASK_BYTES:
        raise ContractError("v9 job charter task is absent or oversized")
    raw_worktree = Path(worktree)
    if raw_worktree.is_symlink():
        raise ContractError("isolated worktree path is a symlink")
    worktree = raw_worktree.resolve(strict=True)
    _refuse_project_flow_in_worktree(worktree, project_root)
    if _git(worktree, "rev-parse", "HEAD") != source_commit:
        raise ContractError("isolated worktree does not match pinned source commit")
    sources = {name: {"path": str(path.relative_to(project_root)),
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for name, path in (("requirements", requirements), ("acceptance", acceptance))}
    # Readiness is credentialless and precedes any durable attempt or send.
    runtime_identity = require_ready()
    execution_dir = run_dir / "execution"
    execution_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(execution_dir, 0o700)
    attempt_id = uuid.uuid4().hex
    attempt_dir = execution_dir / attempt_id
    attempt_dir.mkdir(mode=0o700)
    (attempt_dir / "checkpoints").mkdir(mode=0o700)
    for path, name in ((requirements, "requirements.snapshot.md"), (acceptance, "acceptance.snapshot.md"),
                       (manifest, "manifest.snapshot.json"), (charter, "job-charter.snapshot.json")):
        _write_snapshot(attempt_dir / name, path.read_bytes())
    charter_data = json.loads(charter.read_text())
    baseline_contract = charter_data.get("baseline")
    if (not isinstance(baseline_contract, dict)
            or set(baseline_contract) != {"kind", "diff_sha256"}):
        raise ContractError("v9 job baseline is invalid")
    current_diff = _git(worktree, "diff", "HEAD", "--").encode()
    if baseline_contract["kind"] == "clean":
        if (_git(worktree, "status", "--porcelain", "--untracked-files=all").splitlines()
                or current_diff or baseline_contract["diff_sha256"] != hashlib.sha256(b"").hexdigest()):
            raise ContractError("v9 isolated worktree baseline is not clean")
    elif baseline_contract["kind"] != "declared_regression" \
            or baseline_contract["diff_sha256"] != hashlib.sha256(current_diff).hexdigest():
        raise ContractError("v9 declared baseline differs from the isolated worktree")
    baseline_files = {}
    for relative in charter_data.get("write_paths", []):
        target = worktree / relative
        if target.is_file() and not target.is_symlink():
            baseline_files[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    baseline = {"regression_diff_sha256": baseline_contract["diff_sha256"],
                "source_commit": source_commit, "files": baseline_files}
    write_atomic(attempt_dir / "baseline.json", canonical(baseline) + "\n", mode=0o600)
    sealed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    normalized_availability = [normalize_availability(item) for item in availability]
    policy = effective_policy or merge_selection_policy(framework_policy or {}, administrator_policy, project_policy, run_policy)
    charter_digest = digest({"requirements": sources["requirements"]["sha256"],
                             "acceptance": sources["acceptance"]["sha256"]})
    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    generation = delivery.get("owner_generation") if isinstance(delivery, dict) else None
    if (not isinstance(delivery, dict) or delivery.get("owner_status") != "active"
            or type(generation) is not int or generation < 1
            or not isinstance(delivery.get("charter_digest"), str)
            or not isinstance(delivery.get("lead_claim_digest"), str)):
        raise ContractError("v9 delivery authority is absent or stale")
    projected_limits, _ = project_envelope_limits(authority["charter"]["limits"])
    projected_limits["max_actions"] = min(MAX_MANAGER_CALLS + MAX_ACTIONS,
                                          projected_limits["max_manager_calls"] + projected_limits["max_delegations"])
    envelope = {
        "schema_version": 1, "execution_protocol_version": 9, "work_id": work_id,
        "maf_runtime": runtime_identity,
        "attempt_id": attempt_id, "charter_digest": charter_digest,
        "manifest_digest": manifest_digest, "run_protocol_revision": 2,
        "logical_assignments": logical_assignments,
        "job_charter_digest": hashlib.sha256(charter.read_bytes()).hexdigest(),
        "selection_inputs": {"policy": policy, "catalog": catalog, "availability": normalized_availability},
        "selection_input_digests": {"policy": digest(policy), "catalog": digest(catalog),
                                    "availability": digest(normalized_availability)},
        # Reserve one bounded manager/producer repair pair for a recoverable
        # chartered-test failure. The retry remains subject to the same sealed
        # assignment, provider selection, scope, and test contracts.
        "limits": projected_limits,
        "checkpoint_dir": str(attempt_dir / "checkpoints"),
        "charter_sources": sources, "source_commit": source_commit, "worktree": str(worktree),
        "delivery_charter_digest": delivery["charter_digest"],
        "delivery_lead_claim_digest": delivery["lead_claim_digest"],
        "delivery_lead_claim": {"generation": generation},
    }
    envelope["selection_authority"] = seal_selection_authority(
        work_id=work_id, attempt_id=attempt_id, charter_digest=charter_digest,
        manifest_digest=manifest_digest, generation=generation, sealed_at=sealed_at,
        logical_assignments=logical_assignments, policy=policy, catalog=catalog,
        availability=normalized_availability, independence_constraints=independence_constraints,
    )
    # The ledger validator is the final authority check before any on-disk
    # attempt exists. A malformed configuration must leave no send-capable run.
    envelope_digest(envelope)
    ledger = ExecutionLedger(execution_dir / "ledger.sqlite")
    with delivery_authority_guard(run_dir, envelope):
        ledger.create_attempt(envelope)
    write_atomic(attempt_dir / "envelope.json", canonical(envelope) + "\n", mode=0o600)
    return envelope, task, attempt_dir, ledger


def _hosted_adapter_available(provider: str) -> bool:
    """Whether the local adapter exists and reports an authenticated session.

    The status commands are bounded local CLI observations. They do not send
    the chartered task or expose credential material, so an authentication
    refusal remains safe evidence for pre-send candidate selection.
    """
    executable = {"claude": "claude", "codex": "codex"}.get(provider)
    if executable is None or shutil.which(executable) is None:
        return False
    if provider == "claude":
        credential = Path(os.environ.get("HOME", "")) / ".claude" / ".credentials.json"
    else:
        credential = Path(os.environ.get(
            "CODEX_HOME", str(Path(os.environ.get("HOME", "")) / ".codex")
        )) / "auth.json"
    # Hosted workers run with isolated homes. A host login that cannot be
    # copied into that home is not usable readiness evidence.
    if not credential.is_file() or credential.is_symlink():
        return False
    command = [executable, "auth", "status"] if provider == "claude" else [executable, "login", "status"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    if provider == "claude":
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False
        return isinstance(payload, dict) and payload.get("loggedIn") is True
    return (result.stdout + result.stderr).strip().startswith("Logged in")


def _candidate_readiness(candidate: dict[str, Any], *, local_models: set[str],
                         local_error: str | None, observed: str, expires: str,
                         clock: datetime) -> dict[str, Any]:
    provider, model = candidate.get("provider"), candidate.get("model")
    enabled = candidate.get("enabled") is True
    if provider == "ollama":
        ready = enabled and model in local_models
        state = "ready" if ready else ("unknown" if local_error else "unavailable")
        code = "model_present" if ready else (local_error or "model_absent")
    elif provider in {"claude", "codex"}:
        ready = enabled and _hosted_adapter_available(provider)
        state = "ready" if ready else "unavailable"
        code = "authentication_ready" if ready else "authentication_unavailable"
    else:
        state, code = "unavailable", "adapter_unavailable"
    return normalize_availability({
        "candidate_id": candidate.get("candidate_id"), "state": state,
        "observed_at": observed, "expires_at": expires, "evidence_code": code,
        "probe_version": "availability-v1",
    }, now=clock)


def flow_owned_v9_selection_inputs(project_root: Path, *, now: datetime | None = None) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Load the administrator ceiling and bounded readiness facts for v9.

    Administrator configuration owns exact candidate declarations. Project
    configuration may only disable or lower limits on known candidates. Discovery never
    invents candidates or enables a disabled one. Hosted readiness requires an
    eligible credential artifact plus a bounded, authenticated local CLI status
    observation. Only controlled evidence codes are retained; credential material
    and raw command output are never persisted in selection evidence.
    """
    framework = read_toml(SCAFFOLD_DIR / "flow.toml")
    administrator_path = USER_OVERLAY_DIR / "flow.toml"
    administrator = read_toml(administrator_path) if administrator_path.is_file() else {}
    project_path = project_root / ".flow" / "flow.toml"
    project = read_toml(project_path) if project_path.is_file() else {}
    raw_catalog = administrator.get("provider_candidates", framework.get("provider_candidates", []))
    if not isinstance(raw_catalog, list) or not raw_catalog:
        raise ContractError("Flow provider_candidates configuration is absent")
    catalog = [dict(item) for item in raw_catalog if isinstance(item, dict)]
    if len(catalog) != len(raw_catalog):
        raise ContractError("Flow provider_candidates configuration is invalid")
    adapter_ceilings = {
        "ollama": ({"manage", "read", "edit", "verify", "collect"},
                   {"structured_output", "structured_edit", "evidence_collection"}),
        "claude": ({"manage", "read", "edit", "verify", "collect"},
                   {"structured_output", "structured_edit", "evidence_collection"}),
        "codex": ({"manage", "read", "edit", "verify", "collect"},
                  {"structured_output", "structured_edit", "evidence_collection"}),
    }
    identities: dict[str, dict[str, Any]] = {}
    for candidate in catalog:
        candidate_id, provider = candidate.get("candidate_id"), candidate.get("provider")
        ceiling = adapter_ceilings.get(provider)
        if (not isinstance(candidate_id, str) or not candidate_id or candidate_id in identities
                or ceiling is None or not set(candidate.get("operations", [])).issubset(ceiling[0])
                or not set(candidate.get("capabilities", [])).issubset(ceiling[1])):
            raise ContractError("administrator provider candidate exceeds Flow adapter ceiling")
        identities[candidate_id] = candidate
    overrides = project.get("provider_candidates", [])
    if not isinstance(overrides, list):
        raise ContractError("project provider_candidates must be an array")
    allowed_override_fields = {"candidate_id", "enabled", "max_input_bytes", "max_output_bytes", "max_context_tokens"}
    for override in overrides:
        if not isinstance(override, dict) or not set(override).issubset(allowed_override_fields) \
                or override.get("candidate_id") not in identities:
            raise ContractError("project provider candidate may only narrow a known candidate")
        target = identities[override["candidate_id"]]
        if override.get("enabled") is True and target.get("enabled") is not True:
            raise ContractError("project provider candidate cannot enable an administrator-disabled candidate")
        if "enabled" in override:
            target["enabled"] = override["enabled"]
        for field in ("max_input_bytes", "max_output_bytes", "max_context_tokens"):
            if field in override:
                value = override[field]
                if type(value) is not int or value < 0 or (field in target and value > target[field]):
                    raise ContractError("project provider candidate limit may only narrow")
                target[field] = value
    policy = merge_selection_policy(framework.get("provider_selection", {}),
                                    administrator.get("provider_selection"),
                                    project.get("provider_selection"))
    clock = now or datetime.now(timezone.utc)
    try:
        local_models = discover_ollama_models()
        local_error = None
    except AvailabilityError:
        local_models, local_error = set(), "probe_failed"
    observed = clock.isoformat().replace("+00:00", "Z")
    expires = (clock + timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    availability = []
    for candidate in catalog:
        availability.append(_candidate_readiness(candidate, local_models=local_models,
                                                   local_error=local_error, observed=observed,
                                                   expires=expires, clock=clock))
    return catalog, policy, availability


def logical_assignments_from_charter(work_id: str, *, root: Path) -> list[dict[str, Any]]:
    """Project the approved provider-neutral v9 assignments without invention."""
    run_dir = root / ".flow" / "runs" / work_id
    state = run_status(work_id, root=root)
    if state.get("pending_lifecycle_event"):
        raise ContractError("lifecycle event projection repair is required before v9 execution")
    charter_rel = state.get("artifacts", {}).get("job_charter")
    if not charter_rel:
        raise ContractError("approved v9 job charter artifact is absent")
    charter = _run_file(root, run_dir, charter_rel)
    approved_charter_digest = (state.get("approved_artifact_digests") or {}).get("job_charter")
    if (state.get("job_charter_migrations") and (not isinstance(approved_charter_digest, str)
            or hashlib.sha256(charter.read_bytes()).hexdigest() != approved_charter_digest)):
        raise ContractError("approved v9 job charter digest is absent or stale")
    raw = json.loads(charter.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("write_paths"), list) or not raw["write_paths"]:
        raise ContractError("approved v9 job charter has no edit scope")
    assignments = raw.get("logical_assignments")
    if not isinstance(assignments, list) or not assignments:
        raise ContractError("approved v9 job charter has no sealed logical assignments")
    assignments = deepcopy(assignments)
    # Reuse the envelope validator's closed assignment/DAG checks before any
    # selection authority or provider send exists.
    probe = {
        "schema_version": 1, "execution_protocol_version": 9,
        "work_id": work_id, "attempt_id": "projection-check",
        "charter_digest": "0" * 64, "manifest_digest": "0" * 64,
        "run_protocol_revision": 2, "logical_assignments": assignments,
        "selection_inputs": {}, "selection_input_digests": {},
        "selection_authority": {}, "limits": {}, "checkpoint_dir": "projection-check",
        "delivery_charter_digest": "0" * 64, "delivery_lead_claim_digest": "0" * 64,
        "delivery_lead_claim": {"generation": 1},
    }
    try:
        validate_envelope(probe)
    except ContractError as exc:
        # The synthetic probe intentionally has no selection authority. Only
        # assignment errors are useful here; real preparation validates the
        # complete envelope.
        if "logical assignment" in str(exc) or "logical requirements" in str(exc):
            raise
    by_operation = {
        operation: {item["assignment_id"] for item in assignments
                    if item["requirements"].get("operation") == operation}
        for operation in ("edit", "collect", "verify")
    }
    expected = {
        "edit": set(raw.get("producer_instance_ids", [])),
        "collect": set(raw.get("evidence_collector_instance_ids", [])),
        "verify": set(raw.get("verifier_instance_ids", [])),
    }
    if by_operation != expected:
        raise ContractError("approved v9 logical assignments conflict with charter topology")
    if len([item for item in assignments if item["requirements"].get("operation") == "manage"]) != 1:
        raise ContractError("approved v9 job charter requires exactly one logical manager")
    if len(by_operation["edit"]) != 1:
        raise ContractError("approved v9 job charter requires exactly one producer assignment")
    if not any(item["requirements"]["operation"] == "verify" for item in assignments):
        raise ContractError("approved v9 job charter has no verifier assignment")
    producer_ids = by_operation["edit"]
    collector_ids = by_operation["collect"]
    for item in assignments:
        operation = item["requirements"].get("operation")
        dependencies = set(item.get("depends_on", []))
        if operation == "collect" and not producer_ids.issubset(dependencies):
            raise ContractError("logical evidence collector must depend on every producer assignment")
        if operation == "verify" and not (producer_ids | collector_ids).issubset(dependencies):
            raise ContractError("logical verifier must depend on every producer and evidence collector assignment")
    return assignments


def independence_constraints_from_assignments(assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seal high-risk verifier topology; concrete families resolve from consumed selections."""
    producers = [item["assignment_id"] for item in assignments
                 if item["requirements"]["operation"] == "edit"]
    collectors = [item["assignment_id"] for item in assignments
                  if item["requirements"]["operation"] == "collect"]
    source_digests = [digest(item["requirements"]) for item in assignments
                      if item["assignment_id"] in producers + collectors]
    return [{"assignment_id": item["assignment_id"], "risk_class": "high",
             "excluded_provider_families": [], "producer_assignment_ids": producers,
             "evidence_collector_assignment_ids": collectors,
             "source_binding_digests": source_digests}
            for item in assignments
            if item["requirements"]["operation"] == "verify"
            and item["requirements"]["risk_class"] == "high"
            and item["requirements"]["independence_required"]]


def provider_selection_probe(work_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """Read-only v9 candidate/readiness diagnostic; it creates no attempt."""
    project_root = (root or repo_root()).resolve()
    catalog, policy, availability = flow_owned_v9_selection_inputs(project_root)
    assignments = logical_assignments_from_charter(work_id, root=project_root)
    independence_constraints = independence_constraints_from_assignments(assignments)
    from provider_selection import select_candidate
    decisions = [{"assignment_id": item["assignment_id"],
                  "decision": select_candidate(item["requirements"], policy, catalog, availability)}
                 for item in assignments]
    return {"schema_version": 1, "work_id": work_id, "policy": policy,
            "catalog": catalog, "availability": availability, "decisions": decisions}


def _v9_readiness_recheck(catalog: list[dict[str, Any]], binding: dict[str, Any]) -> dict[str, Any]:
    """Refresh only the already-selected adapter before its send claim."""
    candidate = next((item for item in catalog if item.get("candidate_id") == binding["candidate_id"]), None)
    if candidate is None:
        raise ContractError("selected v9 candidate is absent from Flow catalog")
    clock = datetime.now(timezone.utc)
    observed = clock.isoformat().replace("+00:00", "Z")
    expires = (clock + timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    try:
        local_models, local_error = discover_ollama_models(), None
    except AvailabilityError:
        local_models, local_error = set(), "probe_failed"
    record = _candidate_readiness(candidate, local_models=local_models, local_error=local_error,
                                  observed=observed, expires=expires, clock=clock)
    # This check contains no adapter call: if it says unavailable, Flow has
    # positive local evidence that the selected provider was not sent anything.
    return {**record, "no_send_observed": record["state"] != "ready"}


def _copy_scoped_tree(source: Path, target: Path, scopes: list[str]) -> None:
    """Copy only chartered readable files into a provider-isolated staging repo."""
    copied: set[Path] = set()
    for relative in scopes:
        scope = Path(relative)
        origin = source / scope
        if origin.is_symlink() or not origin.exists() or not origin.resolve().is_relative_to(source.resolve()):
            raise ContractError("hosted edit scope is absent, linked, or escapes the worktree")
        paths = [origin] if origin.is_file() else sorted(path for path in origin.rglob("*") if path.is_file())
        if any(path.is_symlink() for path in ([origin] if origin.is_file() else origin.rglob("*"))):
            raise ContractError("hosted edit scope contains a symlink")
        for path in paths:
            relative_path = path.relative_to(source)
            if relative_path in copied:
                continue
            copied.add(relative_path)
            destination = target / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def _copy_scoped_commit_tree(source: Path, target: Path, scopes: list[str], commit: str) -> None:
    """Materialize the chartered portion of a pinned Git tree without copying .git."""
    result = subprocess.run(
        ["git", "-C", str(source), "ls-tree", "-rz", commit, "--", *scopes],
        capture_output=True, timeout=15, check=False,
    )
    if result.returncode:
        raise ContractError("hosted edit could not read the pinned source tree")
    for record in filter(None, result.stdout.split(b"\0")):
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, object_id = metadata.decode().split()
        relative = Path(raw_path.decode())
        if kind != "blob" or mode == "120000" or not _path_within_scopes(str(relative), scopes):
            raise ContractError("hosted edit source tree contains an unsafe scoped entry")
        blob = subprocess.run(
            ["git", "-C", str(source), "cat-file", "blob", object_id],
            capture_output=True, timeout=15, check=False,
        )
        if blob.returncode:
            raise ContractError("hosted edit could not read a scoped source blob")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(blob.stdout)
        destination.chmod(0o755 if mode == "100755" else 0o644)


def _staging_snapshot(staging: Path) -> dict[str, tuple[str, int]]:
    snapshot: dict[str, tuple[str, int]] = {}
    for path in sorted(item for item in staging.rglob("*") if ".git" not in item.parts):
        if path.is_symlink():
            raise ContractError("hosted edit staging tree contains a symlink")
        if path.is_file():
            snapshot[str(path.relative_to(staging))] = (
                hashlib.sha256(path.read_bytes()).hexdigest(), stat.S_IMODE(path.stat().st_mode))
    return snapshot


def _clear_staging_worktree(staging: Path) -> None:
    for child in staging.iterdir():
        if child.name == ".git":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()


def _source_merge_base(workspace: Path, source_commit: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(workspace), "merge-base", source_commit, "main"],
        capture_output=True, text=True, timeout=15, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else source_commit


def _apply_scoped_hosted_edit(workspace: Path, staging: Path, write_paths: list[str],
                              before: dict[str, tuple[str, int]]) -> dict[str, Any]:
    """Validate a hosted staging diff and atomically copy approved files back."""
    after = _staging_snapshot(staging)
    changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    if not changed:
        raise ContractError("hosted editor made no edit in the scoped staging workspace")
    if any(path not in after or not _path_within_scopes(path, write_paths) for path in changed):
        raise ContractError("hosted editor changed files outside the approved staging scope")
    prepared: list[dict[str, Any]] = []
    for relative in changed:
        source, target = staging / relative, workspace / relative
        if source.is_symlink() or not source.is_file() or target.is_symlink():
            raise ContractError("hosted editor produced an unsafe scoped file")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        source_mode = stat.S_IMODE(source.stat().st_mode)
        original_mode = stat.S_IMODE(target.stat().st_mode) if target.is_file() else None
        with os.fdopen(fd, "wb") as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), source_mode)
        prepared.append({"relative": relative, "target": target, "temporary": Path(temporary),
                         "original": target.read_bytes() if target.is_file() else None,
                         "original_mode": original_mode})
    applied: list[dict[str, Any]] = []
    try:
        for item in prepared:
            os.replace(item["temporary"], item["target"])
            applied.append(item)
    except OSError as exc:
        rollback_error: OSError | None = None
        for item in reversed(applied):
            try:
                if item["original"] is None:
                    item["target"].unlink(missing_ok=True)
                    continue
                fd, restore = tempfile.mkstemp(prefix=f".{item['target'].name}.restore.",
                                               dir=item["target"].parent)
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(item["original"])
                        handle.flush()
                        os.fsync(handle.fileno())
                        os.fchmod(handle.fileno(), item["original_mode"])
                    os.replace(restore, item["target"])
                finally:
                    with suppress(FileNotFoundError):
                        os.unlink(restore)
            except OSError as rollback_exc:
                rollback_error = rollback_exc
        if rollback_error is not None:
            raise ContractError("hosted scoped edit failed and rollback was incomplete") from rollback_error
        raise ContractError("hosted scoped edit application failed and was rolled back") from exc
    finally:
        for item in prepared:
            with suppress(FileNotFoundError):
                item["temporary"].unlink()
    return {"changed_files": [item["relative"] for item in applied],
            "scope_enforcement": "isolated_staging"}


def _hosted_scoped_edit(
    workspace: Path, *, read_paths: list[str], write_paths: list[str],
    source_commit: str, invoke: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    scopes = list(dict.fromkeys([*read_paths, *write_paths]))
    with tempfile.TemporaryDirectory(prefix="flow-v9-hosted-edit-") as temporary:
        staging = Path(temporary)
        _git(staging, "init", "-q")
        _git(staging, "config", "user.email", "flow@local.invalid")
        _git(staging, "config", "user.name", "Flow")
        merge_base = _source_merge_base(workspace, source_commit)
        _copy_scoped_commit_tree(workspace, staging, scopes, merge_base)
        _git(staging, "add", "--all")
        _git(staging, "commit", "-qm", "Flow scoped merge base")
        _git(staging, "branch", "-M", "main")
        _git(staging, "switch", "-qc", "flow-work")
        if merge_base != source_commit:
            _clear_staging_worktree(staging)
            _copy_scoped_commit_tree(workspace, staging, scopes, source_commit)
            _git(staging, "add", "--all")
            if _git(staging, "status", "--porcelain"):
                _git(staging, "commit", "-qm", "Flow pinned source commit")
        _clear_staging_worktree(staging)
        _copy_scoped_tree(workspace, staging, scopes)
        before = _staging_snapshot(staging)
        result = invoke(staging)
        try:
            applied = _apply_scoped_hosted_edit(workspace, staging, write_paths, before)
        except ContractError as exc:
            # Once the hosted adapter has returned, a rejected or empty staging
            # diff is observed provider evidence. Preserve that distinction so
            # the execution can seal a normal evidence failure instead of
            # falsely requiring uncertain-send reconciliation.
            return {**result, "observed_invalid": True, "detail": str(exc)[:512]}
        return {**result, "scoped_edit": applied}


def _hosted_scoped_read(workspace: Path, *, read_paths: list[str],
                        invoke: Callable[[Path], dict[str, Any]]) -> dict[str, Any]:
    """Run a hosted read-only turn with only chartered material visible."""
    with tempfile.TemporaryDirectory(prefix="flow-v9-hosted-read-") as temporary:
        staging = Path(temporary)
        _copy_scoped_tree(workspace, staging, read_paths)
        return invoke(staging)


def _v9_adapter_for_operation(envelope: dict[str, Any], *, read_paths: list[str],
                              write_paths: list[str]) -> Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]:
    """Return the bounded adapter for the selected binding and logical operation."""
    workspace = Path(envelope["worktree"])
    source_commit = envelope.get("source_commit") or _git(workspace, "rev-parse", "HEAD")
    assignment_by_id = {item["assignment_id"]: item for item in envelope["logical_assignments"]}

    def send(binding: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        assignment = assignment_by_id.get(action["assignment_id"])
        if assignment is None:
            raise ContractError("v9 action has no logical assignment")
        operation = assignment["requirements"]["operation"]
        provider, model = binding["provider"], binding["model"]
        instructions, task = assignment["instructions"], action["task"]
        # Hosted provider workers remain bounded. Ollama is local and has no
        # elapsed-time deadline; explicit cancellation still interrupts its
        # socket through local_worker.
        timeout = {
            "manage": 60,
            "read": 120,
            "edit": 600,
            "collect": 600,
            "verify": 600,
        }[operation]
        if provider == "ollama":
            if operation == "edit":
                try:
                    bundle = ollama_source_bundle(workspace, write_paths)
                    proposal = propose_ollama_edits(bundle, task, model=model,
                                                    attempt_id=action["attempt_id"], timeout_seconds=None)
                    applied = apply_ollama_edits(workspace, bundle, proposal, write_scopes=write_paths,
                                                  expected_model=model)
                except ContractError as exc:
                    # A structured response or a fully rolled-back application
                    # failure is observed evidence, not an uncertain send.
                    return {"provider": provider, "model": model, "operation": operation,
                            "observed_invalid": True, "detail": str(exc)[:512]}
                return {"provider": provider, "model": model, "operation": operation, "applied": applied}
            if operation == "manage" and "next_speaker.answer must be exactly one of " in task:
                match = re.search(r"next_speaker\.answer must be exactly one of (\[[^\n]+\])", task)
                try:
                    allowed_speakers = json.loads(match.group(1)) if match else None
                except json.JSONDecodeError as exc:
                    raise ContractError("logical manager task has an invalid speaker frontier") from exc
                return call_ollama_manager([{"role": "user", "content": task}], model=model,
                                           attempt_id=action["attempt_id"], timeout_seconds=None,
                                           preserve_observed_invalid=True,
                                           allowed_speakers=allowed_speakers)
            return call_local({"provider": provider, "model": model, "attempt_id": action["attempt_id"],
                               "instructions": instructions, "task": task},
                              correlation_id=action["action_id"], timeout_seconds=None)
        if provider == "claude":
            if operation == "edit":
                return _hosted_scoped_edit(
                    workspace, read_paths=read_paths, write_paths=write_paths,
                    source_commit=source_commit,
                    invoke=lambda staging: call_claude_edit(
                        instructions=instructions, task=task, workspace=staging,
                        model=model, timeout_seconds=timeout, confine_workspace_reads=True),
                )
            return _hosted_scoped_read(
                workspace, read_paths=read_paths,
                invoke=lambda staging: call_claude(
                    instructions=instructions, task=task, workspace=staging,
                    model=model, timeout_seconds=timeout, confine_workspace_reads=True),
            )
        if provider == "codex":
            if operation == "edit":
                return _hosted_scoped_edit(
                    workspace, read_paths=read_paths, write_paths=write_paths,
                    source_commit=source_commit,
                    invoke=lambda staging: call_codex(
                        instructions=instructions, task=task, workspace=staging, model=model,
                        timeout_seconds=timeout, sandbox="workspace-write",
                        confine_workspace_reads=True),
                )
            return _hosted_scoped_read(
                workspace, read_paths=read_paths,
                invoke=lambda staging: call_codex(
                    instructions=instructions, task=task, workspace=staging, model=model,
                    timeout_seconds=timeout, sandbox="read-only", confine_workspace_reads=True),
            )
        raise ContractError("selected v9 provider has no bounded adapter")

    return send


def execute_v9_chartered_job(work_id: str, worktree: Path, source_commit: str, *, root: Path | None = None) -> dict[str, Any]:
    """Default live chartered-job route for new Flow work."""
    project_root = (root or repo_root()).resolve()
    catalog, policy, availability = flow_owned_v9_selection_inputs(project_root)
    assignments = logical_assignments_from_charter(work_id, root=project_root)
    independence_constraints = independence_constraints_from_assignments(assignments)
    state = run_status(work_id, root=project_root)
    charter = _run_file(project_root, project_root / ".flow" / "runs" / work_id,
                        state.get("artifacts", {}).get("job_charter", ""))
    charter_data = json.loads(charter.read_text())
    write_paths = charter_data.get("write_paths") if isinstance(charter_data, dict) else None
    read_paths = charter_data.get("read_paths") if isinstance(charter_data, dict) else None
    if not isinstance(write_paths, list) or not all(isinstance(path, str) and path for path in write_paths):
        raise ContractError("approved v9 job charter has invalid edit scope")
    if not isinstance(read_paths, list) or not all(isinstance(path, str) and path for path in read_paths):
        raise ContractError("approved v9 job charter has invalid read scope")
    envelope, task, _attempt_dir, ledger = prepare_v9_chartered_delivery(
        work_id, worktree, source_commit, root=project_root, logical_assignments=assignments,
        catalog=catalog, availability=availability, effective_policy=policy,
        independence_constraints=independence_constraints,
    )
    result = execute_v9_logical_delivery(
        envelope, task, ledger, _v9_adapter_for_operation(
            envelope, read_paths=read_paths, write_paths=write_paths),
        readiness_recheck=lambda binding: _v9_readiness_recheck(catalog, binding),
    )
    if result.get("status") != "completed":
        return {"attempt_id": envelope["attempt_id"], "status": result.get("status", "refused"),
                "reason": result.get("reason", "logical_delivery_not_completed"),
                "receipt_path": result.get("receipt_path"), **result}
    authority = _sealed_delivery_authority(project_root / ".flow" / "runs" / work_id,
                                           state.get("delivery", {}))
    if "handoff_to_review" not in authority["charter"].get("allowed_lifecycle_operations", []):
        return result
    ok, payload, errors = handoff_to_review(work_id, envelope["attempt_id"],
                                            envelope["selection_authority"]["generation"], root=project_root)
    if not ok:
        return {**result, "status": "handoff_failed", "reason": "; ".join(errors),
                "review_handoff": {"status": "failed", "errors": errors}}
    return {**result, "review_handoff": {"status": "completed", "state": payload["state"]}}


def resume_v9_chartered_job(work_id: str, attempt_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """Continue a v9 charter from a clean completed-action boundary."""
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    execution_dir = run_dir / "execution"
    ledger = ExecutionLedger(execution_dir / "ledger.sqlite")
    snapshot = ledger.snapshot(attempt_id)
    if snapshot["execution_protocol_version"] != 9 or snapshot["work_id"] != work_id:
        raise ContractError("v9 continuation target differs from the requested run")
    if snapshot["status"] != "started":
        raise ContractError("v9 continuation target is already terminal")
    if any(item["status"] != "completed" for item in snapshot["actions"]):
        raise ContractError("v9 continuation requires explicit reconciliation before resume")
    envelope = snapshot["envelope"]
    attempt_dir = execution_dir / attempt_id
    charter_path = attempt_dir / "job-charter.snapshot.json"
    if not charter_path.is_file() or charter_path.is_symlink():
        raise ContractError("v9 continuation job charter snapshot is absent")
    charter = json.loads(charter_path.read_text())
    task = charter.get("task")
    read_paths, write_paths = charter.get("read_paths"), charter.get("write_paths")
    if not isinstance(task, str) or not task.strip():
        raise ContractError("v9 continuation task is absent")
    if not isinstance(read_paths, list) or not all(isinstance(path, str) and path for path in read_paths):
        raise ContractError("v9 continuation read scope is invalid")
    if not isinstance(write_paths, list) or not all(isinstance(path, str) and path for path in write_paths):
        raise ContractError("v9 continuation edit scope is invalid")
    catalog = envelope.get("selection_inputs", {}).get("catalog")
    if not isinstance(catalog, list):
        raise ContractError("v9 continuation selection catalog is absent")
    result = execute_v9_logical_delivery(
        envelope, task, ledger,
        _v9_adapter_for_operation(envelope, read_paths=read_paths, write_paths=write_paths),
        readiness_recheck=lambda binding: _v9_readiness_recheck(catalog, binding),
    )
    if result.get("status") != "completed":
        return result
    state = run_status(work_id, root=project_root)
    authority = _sealed_delivery_authority(run_dir, state.get("delivery", {}))
    if "handoff_to_review" not in authority["charter"].get("allowed_lifecycle_operations", []):
        return result
    ok, payload, errors = handoff_to_review(
        work_id, attempt_id, envelope["selection_authority"]["generation"], root=project_root)
    if not ok:
        return {**result, "status": "handoff_failed", "reason": "; ".join(errors),
                "review_handoff": {"status": "failed", "errors": errors}}
    return {**result, "review_handoff": {"status": "completed", "state": payload["state"]}}


def v9_recovery_status(work_id: str, attempt_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """Return the explicit reconciliation state for a v9 attempt.

    V9 never replays a claimed provider call. A caller must reconcile an
    unknown result from Flow-owned observation, or cancel/abandon it with a
    receipt that preserves the consumed selection.
    """
    project_root = (root or repo_root()).resolve()
    ledger = ExecutionLedger(project_root / ".flow" / "runs" / work_id / "execution" / "ledger.sqlite", read_only=True)
    snapshot = ledger.snapshot(attempt_id)
    if snapshot["execution_protocol_version"] != 9 or snapshot["work_id"] != work_id:
        raise ContractError("v9 recovery target differs from the requested run")
    unresolved = [item["action_id"] for item in snapshot["actions"] if item["status"] in {"started", "unknown"}]
    resume_allowed = snapshot["status"] == "started" and bool(snapshot["actions"]) and not unresolved
    return {"work_id": work_id, "attempt_id": attempt_id, "status": snapshot["status"],
            "reconciliation_required": bool(unresolved), "unresolved_action_ids": unresolved,
            "resume_allowed": resume_allowed,
            "next_action": ("reconcile-observed-result-or-cancel-abandon" if unresolved else
                            "resume-chartered-job" if resume_allowed else "attempt-terminal-or-seal")}


def terminate_v9_delivery(work_id: str, attempt_id: str, *, status: str, actor: str,
                          explanation: str, root: Path | None = None) -> dict[str, Any]:
    """Receipt-seal a v9 cancellation or abandonment without replaying I/O."""
    project_root = (root or repo_root()).resolve()
    execution_dir = project_root / ".flow" / "runs" / work_id / "execution"
    ledger = ExecutionLedger(execution_dir / "ledger.sqlite")
    snapshot = ledger.snapshot(attempt_id)
    if snapshot["execution_protocol_version"] != 9 or snapshot["work_id"] != work_id:
        raise ContractError("v9 termination target differs from the requested run")
    if snapshot["status"] != "started":
        raise ContractError("v9 attempt is already terminal")
    run_dir = execution_dir.parent
    with delivery_authority_guard(run_dir, snapshot["envelope"]):
        sealed = ledger.terminate_v9_attempt(
            attempt_id, status, generation=snapshot["owner_generation"], actor=actor,
            explanation=explanation, cause="operator_" + status,
            receipt_path=execution_dir / attempt_id / "receipt.json",
        )
    return {**sealed, "work_id": work_id, "cause": "operator_" + status,
            "owner_generation": snapshot["owner_generation"], "reaped": []}
