"""Flow-owned dispatch boundary for a stock Magentic Delivery Lead (v5)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from contextlib import nullcontext, suppress
from functools import partial
from pathlib import Path
from typing import Any, Callable

from execution_contracts import (ContractError, canonical, digest, envelope_digest,
                                 expected_magentic_action_id, expected_manager_call_id,
                                 expected_replan_id, validate_action, validate_manager_call,
                                 validate_result, validate_receipt)
from execution_ledger import ExecutionLedger, utc_now
from delivery_control import delivery_authority_guard
from delivery_projection import lead_claim_active
from delivery_recovery import (ATTEMPT_TERMINAL, CONTINUATION_EPOCHS_V5_ONLY, ENVELOPE_CHANGED, RecoveryRefused,
                               SIBLING_ATTEMPT_NOT_TERMINAL,
                               V6_INSPECTION_ONLY, V7_NOT_RECOVERABLE, WORKTREE_DRIFT, build_recovery_block,
                               rebuild_chartered_evidence_plan, recovery_eligibility, restore_position,
                               runtime_outcome)
from delivery_contracts import (DeliveryContractError, digest as delivery_digest, validate_delivery_charter,
                                validate_shaper_contract)
from execution_gateway import _effective_specialist_for, _run_file, _write_snapshot
from fsutil import repo_root, write_atomic
from local_worker import call_local
from claude_worker import call_claude
from claude_edit_worker import MAX_EVENT_BYTES, MAX_TRACE_BYTES, _stream_result, call_claude_edit
from codex_worker import call_codex
from maf_supervisor import MafTransportError, run_maf_delivery
from orchestration import validate_orchestration
from runstate import status as run_status
from verifier_contracts import VERIFIER_CONTRACT_INSTRUCTION, evaluate_candidate, provider_binding_mismatch

APPROVED_PATHS = ("cli/codex_worker.py", "tests/test_codex_worker.py")
ROSTER_IDS = ("claude-implementer", "local-analyst", "local-verifier")
MAX_TASK_BYTES = 4096


def _safe_job_path(path: Any) -> str:
    if (not isinstance(path, str) or not path or Path(path).is_absolute()
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or "\\" in path or ".git" in path.split("/")):
        raise ContractError("job path is not a safe relative path")
    return path


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
    if (not isinstance(argv, list) or len(argv) != 8
            or any(not isinstance(arg, str) or not arg or len(arg) > 256 or "\x00" in arg for arg in argv)
            or argv[0] not in {"python3", "python3.12", "/opt/homebrew/bin/python3.12"}
            or argv[1:6] != ["-m", "unittest", "discover", "-s", "tests"]
            or argv[6] != "-p"
            or type(timeout) is not int or not 1 <= timeout <= 3600):
        raise ContractError("targeted test argv or deadline is unsupported")
    if not argv[7].startswith("test_") or not argv[7].endswith(".py") or not argv[7][5:-3].replace("_", "").isalnum():
        raise ContractError("targeted test pattern is unsafe")
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
    if not isinstance(charter, dict) or set(charter) != {"task", "read_paths", "write_paths", "test", "producer_instance_ids", "verifier_instance_ids", "baseline"}:
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
        if read_only != (provider == "ollama"):
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
    producers, verifiers = charter["producer_instance_ids"], charter["verifier_instance_ids"]
    if any(item not in by_id or "edit" not in by_id[item]["capabilities"] for item in producers):
        raise ContractError("producer is not an approved editor")
    if any(item not in by_id or by_id[item]["capabilities"] != ["read"] for item in verifiers) or set(producers) & set(verifiers):
        raise ContractError("verifier is not an independent read-only specialist")
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
        if not diff or baseline["diff_sha256"] != hashlib.sha256(diff).hexdigest() or any(line[3:] not in charter["write_paths"] for line in lines):
            raise ContractError("declared regression differs from pinned baseline")
    else:
        raise ContractError("job baseline kind is unsupported")
    job_baseline = {key: baseline[key] for key in ("kind", "diff_sha256")}
    baseline = {"regression_diff_sha256": baseline["diff_sha256"], "source_commit": source_commit,
                "files": {path: hashlib.sha256((worktree / path).read_bytes()).hexdigest() for path in charter["write_paths"] if (worktree / path).is_file()}}
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
                    "test": charter["test"], "producer_instance_ids": producers, "verifier_instance_ids": verifiers}
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
                "limits": {"max_delegations": canonical_limits["delegations"],
                           "max_concurrent": canonical_limits["concurrency"],
                           "max_replans": canonical_limits["replans"],
                           "max_runtime_seconds": canonical_limits["runtime_seconds"],
                           "max_manager_calls": canonical_limits["max_manager_calls"],
                           "max_manager_rounds": canonical_limits["max_manager_rounds"],
                           "max_paid_worker_calls": canonical_limits["max_paid_worker_calls"],
                           "max_verifier_calls": canonical_limits["max_verifier_calls"]}}
    if predecessors:
        # Added only when non-empty, so a first attempt stays byte-identical.
        envelope["predecessors"] = predecessors
    envelope_digest(envelope)
    write_atomic(attempt_dir / "envelope.json", canonical(envelope) + "\n", mode=0o600)
    write_atomic(attempt_dir / "baseline.json", canonical(baseline) + "\n", mode=0o600)
    ledger = ExecutionLedger(execution_dir / "ledger.sqlite")
    ledger.create_attempt(envelope)
    return envelope, task, attempt_dir, ledger


def _normalized_manager_request(envelope: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    messages = message.get("messages")
    if not isinstance(messages, list) or not messages or len(canonical(messages).encode()) > 32000:
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
    return _execute_prepared_delivery(envelope, task, attempt_dir, ledger,
                                      manager_adapter=manager_adapter, worker_adapter=worker_adapter,
                                      supervisor=supervisor, test_runner=None, python_path=None,
                                      generation=envelope["delivery_lead_claim"]["generation"],
                                      seal_hook=seal_hook)


def _verify_chartered_edit(worktree: Path, baseline: dict[str, Any], attempt_dir: Path,
                           job: dict[str, Any], *, record: bool = True) -> dict[str, Any]:
    if _git(worktree, "rev-parse", "HEAD") != baseline["source_commit"]:
        raise ContractError("editor changed the pinned source commit")
    allowed = set(job["write_paths"])
    status = _git(worktree, "status", "--porcelain", "--untracked-files=all").splitlines()
    changed = [line[3:] for line in status]
    if not changed or any(line[:2] not in {" M", "M ", "??"} or path not in allowed for line, path in zip(status, changed)):
        raise ContractError("editor changed files outside the approved job scope")
    if not any((worktree / path).is_file() and hashlib.sha256((worktree / path).read_bytes()).hexdigest() != baseline["files"].get(path) for path in changed):
        raise ContractError("editor produced no observed change")
    diff = _git(worktree, "diff", "HEAD", "--", *job["write_paths"]).encode()
    for path in changed:
        if path not in baseline["files"]:
            diff += ("\nNEW FILE " + path + "\n").encode() + (worktree / path).read_bytes()
    if not diff or len(diff) > 32768:
        raise ContractError("chartered edit diff is empty or oversized")
    diff_path = attempt_dir / "repair.diff"
    if diff_path.exists():
        if diff_path.is_symlink() or diff_path.read_bytes() != diff:
            raise ContractError("recorded chartered diff changed")
    elif record:
        _write_snapshot(diff_path, diff)
    return {"changed_files": changed, "diff_sha256": hashlib.sha256(diff).hexdigest(),
            "diff_path": str(diff_path),
            "files": {path: hashlib.sha256((worktree / path).read_bytes()).hexdigest() for path in changed}}


def _run_chartered_test(worktree: Path, job: dict[str, Any]) -> dict[str, Any]:
    test = _job_test(job["test"])
    try:
        completed = subprocess.run(test["argv"], cwd=worktree, capture_output=True, text=True,
                                   timeout=test["timeout_seconds"], check=False,
                                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    except subprocess.TimeoutExpired as exc:
        raise ContractError("targeted chartered test timed out") from exc
    output = (completed.stdout + completed.stderr)[-8192:]
    if completed.returncode:
        raise ContractError("targeted chartered test failed: " + output[-512:])
    return {"command": test["argv"], "status": "passed", "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


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
        if snapshot.get("recoveries"):
            return snapshot, None
        raise RecoveryRefused(ATTEMPT_TERMINAL)
    try:
        delivery = json.loads((run_dir / "run.json").read_text()).get("delivery")
    except (OSError, json.JSONDecodeError):
        delivery = None
    eligibility = recovery_eligibility(envelope, snapshot, lead_active=lead_claim_active(delivery, envelope))
    if not eligibility["recoverable"]:
        raise RecoveryRefused(eligibility["reason"], ", ".join(f"{item['kind']} {item['id']} {item['status']}"
                                                               for item in eligibility["blockers"]))
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
                quarantined=quarantine)
        generation = claim["generation"]
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
        row = next(item for item in state["actions"] if item["action_id"] == eligibility["action_id"])
        action = row["request"]
        checkpoint = ledger.read_magentic_checkpoint(attempt_id, "worker", action["action_id"])
        if checkpoint["metadata"]["checkpoint_id"] != action["checkpoint_id"]:
            raise ContractError("Magentic restore checkpoint differs from worker action")
        resume: dict[str, Any] = {"checkpoint_id": action["checkpoint_id"],
                                  "request_id": f"flow-magentic-action-{action['sequence']}",
                                  "action_id": action["action_id"],
                                  **restore_position(envelope, state, checkpoint["metadata"]["ledger_seq"])}
        job = envelope["job_contract"]
        if mode == "answer":
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
        tests = (test_runner or partial(_run_chartered_test, job=job))(worktree)
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


def recover_delivery(work_id: str, attempt_id: str, *, root: Path | None = None,
                     actor: str = "codex-assisted-recovery", python_path: str | None = None,
                     manager_adapter: Callable[..., dict[str, Any]] | None = None,
                     worker_adapter: Callable[..., dict[str, Any]] | None = None,
                     supervisor: Callable[..., dict[str, Any]] | None = None,
                     test_runner: Callable[[Path], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Resolve one observed v5 Claude result and resume it; route v6-v8 to chartered recovery."""
    project_root = (root or repo_root()).resolve()
    valid, _, findings = validate_orchestration(work_id, "dispatch", root=project_root)
    if not valid:
        raise ContractError("orchestration dispatch invalid: " + "; ".join(f.message for f in findings))
    attempt_dir = project_root / ".flow" / "runs" / work_id / "execution" / attempt_id
    peek = _peek_snapshot(attempt_dir.parent / "ledger.sqlite", attempt_id)
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


def _verifier_provider_task(task: str, diff: str, diff_sha256: str, *, structured: bool) -> str:
    """Build the exact evidence-bearing verifier input Flow sends and digests."""
    text = (task + "\n\nFlow-verified complete bounded diff for this review:\n"
            + diff + "\nTargeted test: passed. Diff SHA-256: " + diff_sha256)
    return text + VERIFIER_CONTRACT_INSTRUCTION if structured else text


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
                   continuation_epoch_id: str | None) -> tuple[dict[str, Any], str, str]:
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
        if envelope.get("predecessors"):
            receipt["lineage_usage"] = ledger.lineage_usage(aid)
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
        if event_size > MAX_EVENT_BYTES:
            raise ContractError("Claude event trace exceeds limit")
        receipt["evidence"]["event_trace"] = {
            "path": event_path.name, "sha256": hashlib.sha256(event_path.read_bytes()).hexdigest(),
            "bytes": event_size}
    if continuation_epoch_id:
        epoch = ledger.continuation_snapshot(continuation_epoch_id)
        receipt["evidence"]["continuation"] = {
            "epoch_id": continuation_epoch_id,
            "original_receipt_sha256": epoch["receipt_sha256"],
            "checkpoint_sha256": epoch["checkpoint_sha256"],
            "resolution_id": epoch["resolution_id"]}
    return receipt, terminal, reason


def _execute_prepared_delivery(envelope: dict[str, Any], task: str, attempt_dir: Path,
                               ledger: ExecutionLedger, **kwargs: Any) -> dict[str, Any]:
    """Run one prepared attempt; a live v8 run holds the attempt's recovery fence throughout."""
    if envelope["execution_protocol_version"] == 8 and kwargs.get("recovery") is None:
        with ledger.recovery_lock(envelope["attempt_id"], holder="live"):
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
    task += ("\n\nFlow-verified execution facts:\n"
             "- The isolated worktree is pinned to source commit " + source_commit + ".\n"
             + (("- The approved baseline is " + job["baseline"]["kind"] + ".\n") if chartered else "- The approved regression test is already present and failed before this job's first provider send. Do not ask a specialist to create or rerun that prerequisite.\n")
             +
             "- Read-only analyst and verifier specialists can analyze supplied task text only; they cannot read files,"
             " run commands, or edit the worktree.\n"
             "- The approved editor may edit only the charter's allowed paths. Flow verifies the diff and runs"
             " the targeted test after that edit; the full suite is an acceptance check.\n"
             + "".join(f"- Predecessor attempt {item['attempt_id']} ended {item['terminal_status']} under lead"
                       f" generation {item['lead_generation']}; its evidence is not reused.\n"
                       for item in envelope.get("predecessors", [])))
    manager_adapter = manager_adapter or _default_manager_adapter
    worker_adapter = worker_adapter or partial(_default_worker_adapter, trace_dir=attempt_dir)
    test_runner = test_runner or (partial(_run_chartered_test, job=job) if chartered else _run_targeted_test)
    verify_edit = (partial(_verify_chartered_edit, job=job) if chartered else _verify_edit)
    edit_evidence: dict[str, Any] | None = None
    test_evidence: dict[str, Any] | None = None
    failure = ""
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
        verifier_task = _verifier_provider_task(prior_verifier[-1]["request"]["task"], (attempt_dir / "repair.diff").read_text(),
                                                edit_evidence["diff_sha256"], structured=structured_verifier)
        verifier_input_sha256 = hashlib.sha256(verifier_task.encode()).hexdigest()

    def on_manager(message: dict[str, Any]) -> str:
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
        if decision.get("replayed") and isinstance(decision.get("result"), dict):
            observed = decision["result"].get("output")
            if isinstance(observed, str) and observed.strip():
                return observed
        if decision.get("replayed") and not decision["allowed"]:
            raise ContractError("Magentic manager call needs reconciliation: " + decision["reason"])
        if not decision["allowed"]:
            raise ContractError("Magentic manager call denied: " + decision["reason"])
        with authority_guard(), ledger.send_lock():
            ledger.assert_owner(aid, generation)
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
        action = _normalized_action(envelope, message)
        is_verifier = action["instance_id"] in job["verifier_instance_ids"] if chartered else action["assignment_id"] == "local-verifier"
        is_producer = action["instance_id"] in job["producer_instance_ids"] if chartered else action["assignment_id"] == "claude-implementer"
        if chartered and action["provider"] in {"claude", "codex"} and not is_producer:
            raise ContractError("selected editor is not eligible to produce this job")
        if is_verifier and (edit_evidence is None or test_evidence is None):
            raise ContractError("Magentic verifier selected before Flow verified Claude repair")
        with authority_guard():
            decision = ledger.decide(envelope, action, generation=generation)
            regranted = False
            if (recovery is not None and decision.get("replayed") and not decision["allowed"]
                    and decision["reason"] == "recovery_unconsumed_grant"
                    and action["action_id"] in recovery.get("regrantable_action_ids", [])):
                decision = ledger.regrant_recovered_action(envelope, action, generation=generation)
                regranted = decision["allowed"]
        if decision.get("replayed") and isinstance(decision.get("result"), dict):
            return _completed_reply(ledger, envelope, attempt_dir, action, decision["result"],
                                    is_verifier=is_verifier, is_producer=is_producer,
                                    edit_evidence=edit_evidence, test_evidence=test_evidence,
                                    generation=generation, authority_guard=authority_guard)
        if decision.get("replayed") and not decision["allowed"]:
            raise ContractError("Magentic specialist call needs reconciliation: " + decision["reason"])
        if not decision["allowed"]:
            return {"status": "denied", "action_id": action["action_id"], "reason": decision["reason"], "summary": "Flow denied this specialist call"}
        provider_action = action
        if is_verifier:
            provider_task = _verifier_provider_task(action["task"], (attempt_dir / "repair.diff").read_text(),
                                                    edit_evidence["diff_sha256"], structured=structured_verifier)
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

    try:
        runner_kwargs = {"python_path": python_path, "timeout_s": envelope["limits"].get("max_runtime_seconds", 900)}
        if resume is not None:
            runner_kwargs["resume"] = resume
        outcome = (supervisor or run_maf_delivery)(envelope, task, on_manager, on_action, **runner_kwargs)
        if outcome.get("attempt_id") != aid:
            raise ContractError("Magentic finished a different attempt")
    except Exception as exc:
        failure = str(exc)
        recoverable_transport_failure = isinstance(exc, MafTransportError)
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
        blocking = [item.get("action_id") or item.get("call_id") for item in actions + manager_calls
                    if item["status"] in {"started", "unknown"}]
        return {"attempt_id": aid, "status": "interrupted", "reason": cause, "detail": failure[:512],
                "interruption_id": interruption["interruption_id"], "receipt_path": None,
                "resume_available": not uncertain, "blocking": blocking}
    if structured_verifier:
        with authority_guard(), ledger.send_lock():
            ledger.record_runtime_outcome(aid, failure=failure, transport=recoverable_transport_failure,
                                          generation=generation)
        hook("after-runtime-outcome")
    if not continuation_epoch_id:
        return _seal_attempt(envelope, attempt_dir, ledger, snapshot, failure=failure,
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
                  failure: str, edit_evidence: dict[str, Any] | None, test_evidence: dict[str, Any] | None,
                  verifier_input_sha256: str | None, generation: int, authority_guard: Callable[[], Any],
                  hook: Callable[[str], None]) -> dict[str, Any]:
    """Build, validate, write, and seal an attempt receipt under the owner fence."""
    aid = envelope["attempt_id"]
    receipt, terminal, reason = _build_receipt(envelope, attempt_dir, ledger, snapshot, failure=failure,
                                               edit_evidence=edit_evidence, test_evidence=test_evidence,
                                               verifier_input_sha256=verifier_input_sha256,
                                               continuation_epoch_id=None)
    validate_receipt(envelope, receipt)
    hook("after-receipt-draft")
    receipt_path = attempt_dir / "receipt.json"
    with authority_guard(), ledger.send_lock():
        ledger.assert_owner(aid, generation)
        write_atomic(receipt_path, canonical(receipt) + "\n", mode=0o600)
        hook("before-finish-attempt")
        ledger.finish_attempt(aid, terminal, reason, str(receipt_path), generation=generation)
    return {"attempt_id": aid, "status": terminal, "reason": reason, "receipt_path": str(receipt_path),
            "evidence": receipt["evidence"]}


def _default_manager_adapter(message: dict[str, Any], *, envelope: dict[str, Any], workspace: Path) -> dict[str, Any]:
    turns = []
    for item in message["messages"]:
        contents = item.get("contents") if isinstance(item, dict) else None
        role = item.get("role") if isinstance(item, dict) else None
        if not isinstance(role, str) or not isinstance(contents, list) or not contents:
            raise ContractError("stock manager prompt structure is invalid")
        parts = [part.get("text") for part in contents if isinstance(part, dict) and part.get("type") == "text"]
        if len(parts) != len(contents) or any(not isinstance(part, str) for part in parts):
            raise ContractError("stock manager message contains unsupported content")
        turns.append(f"{role}:\n" + "\n".join(parts))
    prompt = "\n\n".join(turns)
    if not prompt.strip():
        raise ContractError("stock manager prompt text is absent")
    timeout_seconds = min(120, envelope.get("limits", {}).get("max_runtime_seconds", 120))
    if envelope["manager"].get("provider", "claude") == "claude":
        result = call_claude(instructions="stock Magentic manager", task="model response",
                             prompt_override=prompt, workspace=workspace,
                             model=envelope["manager"]["model"], timeout_seconds=timeout_seconds,
                             max_output_bytes=32768)
    elif envelope["manager"]["provider"] == "codex":
        result = call_codex(instructions="Respond to the stock Magentic manager request only. Return the requested response text without editing files.",
                            task=prompt, workspace=workspace, model=envelope["manager"]["model"],
                            timeout_seconds=timeout_seconds, sandbox="read-only",
                            max_prompt_bytes=32768, max_output_bytes=32768)
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
                            trace_dir: Path | None = None) -> dict[str, Any]:
    assignment = next(item for item in envelope["roster"] if item["assignment_id"] == action["assignment_id"])
    timeout_seconds = min(300, envelope.get("limits", {}).get("max_runtime_seconds", 300))
    if action["provider"] == "ollama":
        structured = (envelope["execution_protocol_version"] == 8
                      and action["instance_id"] in envelope["job_contract"]["verifier_instance_ids"])
        return call_local({**assignment, "task": action.get("provider_task", action["task"]), "attempt_id": envelope["attempt_id"]},
                          correlation_id=action["action_id"], timeout_seconds=min(60, timeout_seconds),
                          structured_verifier=structured)
    if action["provider"] == "claude":
        return call_claude_edit(instructions=assignment["instructions"], task=action["task"],
                                workspace=workspace, model=assignment["model"], timeout_seconds=timeout_seconds,
                                trace_path=(trace_dir / "claude-implementer.debug.log") if trace_dir else None)
    if action["provider"] == "codex" and envelope["execution_protocol_version"] in {6, 7, 8}:
        return call_codex(instructions=assignment["instructions"], task=action["task"],
                          workspace=workspace, model=assignment["model"], timeout_seconds=timeout_seconds)
    raise ContractError("selected specialist provider has no approved adapter")
