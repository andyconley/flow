"""Read-only view of Flow v7 and v8 Delivery Lead projections.

The CLI layer uses this module rather than reconstructing authority from a
receipt.  A v7 execution record remains executable only while its attempt is
started and its current owner generation matches the embedded lead claim.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from delivery_recovery import recovery_eligibility
from execution_contracts import (ContractError, DELIVERY_PROTOCOL_VERSION,
                                 STRUCTURED_VERIFIER_PROTOCOL_VERSION, validate_envelope)
from execution_ledger import ExecutionLedger
from fsutil import repo_root
from legacy_delivery import inspect_legacy_delivery


def lead_claim_active(delivery: Any, envelope: dict[str, Any]) -> bool:
    """Whether run authority still names this envelope's Delivery Lead claim."""
    claim = envelope.get("delivery_lead_claim")
    return (isinstance(delivery, dict) and isinstance(claim, dict)
            and delivery.get("owner_status") == "active"
            and delivery.get("owner_generation") == claim.get("generation")
            and delivery.get("lead_claim_digest") == envelope.get("delivery_lead_claim_digest")
            and delivery.get("charter_digest") == envelope.get("delivery_charter_digest"))


def inspect_delivery_projection(envelope: dict[str, Any], snapshot: dict[str, Any], *,
                                lead_active: bool | None = None, receipt_file: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a stable, non-authorizing v7 or v8 delivery-inspection view.

    ``snapshot`` is the ledger's current snapshot. This function intentionally
    does not grant, recover, or mutate anything. For v8, ``lead_active`` comes
    from run authority: a recovered attempt's ledger fence has moved past the
    envelope's claim generation, so the ledger generation cannot decide it.
    ``receipt_file`` carries the receipt file's digest and whether it holds a
    recovery block.
    """
    validate_envelope(envelope)
    protocol = envelope.get("execution_protocol_version")
    if protocol not in {DELIVERY_PROTOCOL_VERSION, STRUCTURED_VERIFIER_PROTOCOL_VERSION}:
        raise ContractError("delivery inspection requires execution protocol v7 or v8")
    if snapshot.get("attempt_id") != envelope["attempt_id"]:
        raise ContractError("delivery inspection attempt differs from projection")
    claim = envelope["delivery_lead_claim"]
    current_generation = snapshot.get("owner_generation")
    status = snapshot.get("status")
    structured = protocol == STRUCTURED_VERIFIER_PROTOCOL_VERSION and lead_active is not None
    active = status == "started" and (lead_active if structured else current_generation == claim["generation"])
    recovery_view: dict[str, Any] = {}
    if structured:
        eligibility = recovery_eligibility(envelope, snapshot, lead_active=bool(lead_active))
        recoveries = snapshot.get("recoveries", [])
        ledger_sha = snapshot.get("sealed_receipt_sha256")
        file_sha = (receipt_file or {}).get("sha256")
        block_present = (receipt_file or {}).get("recovery_block_present")
        recovery_view = {
            "recovery": {key: eligibility[key] for key in ("recoverable", "reason", "mode", "blockers")},
            "interruptions": snapshot.get("interruptions", []),
            "recoveries": recoveries,
            "predecessors": envelope.get("predecessors", []),
            # The ledger digest is authoritative (R2): a recovered attempt whose
            # receipt lost its recovery block is inconsistent even if the file
            # still validates on its own.
            "sealed_receipt": {"ledger_sha256": ledger_sha, "file_sha256": file_sha,
                               "matches": ledger_sha is not None and ledger_sha == file_sha,
                               "recovery_block_present": block_present,
                               "recovery_block_required": bool(recoveries),
                               "consistent": ledger_sha is None and file_sha is None and status == "started"
                               or (ledger_sha is not None and ledger_sha == file_sha
                                   and bool(block_present) == bool(recoveries))},
        }
    return {
        "execution_protocol_version": protocol,
        "work_id": envelope["work_id"],
        "attempt_id": envelope["attempt_id"],
        "status": status,
        "executable": active,
        "resumable": recovery_view["recovery"]["recoverable"] if structured else active,
        "delivery_lead": {"id": claim["lead_id"], "generation": claim["generation"],
                          "current_generation": current_generation, "active": active},
        "contracts": {field: envelope[field] for field in ("shaper_contract_digest", "delivery_charter_digest", "handoff_digest", "delivery_lead_claim_digest")},
        "provider_choices": [item["request"]["provider_choice"] for item in snapshot.get("actions", [])
                             if isinstance(item, dict) and isinstance(item.get("request"), dict)
                             and "provider_choice" in item["request"]],
        **({"verifier_evaluations": snapshot.get("verifier_evaluations", []),
            "verifier_usage": snapshot.get("verifier_usage")}
           if protocol == STRUCTURED_VERIFIER_PROTOCOL_VERSION else {}),
        **recovery_view,
    }


def inspect_delivery(work_id: str, attempt_id: str | None = None, *, root: Path | None = None) -> dict[str, Any]:
    """Inspect sealed delivery authority and optional execution evidence without dispatch."""
    project_root = (root or repo_root()).resolve()
    run_dir = project_root / ".flow" / "runs" / work_id
    run_path = run_dir / "run.json"
    if not run_path.is_file() or run_path.is_symlink():
        raise ContractError("delivery run is absent")
    state = json.loads(run_path.read_text())
    delivery = state.get("delivery") if isinstance(state.get("delivery"), dict) else None
    result: dict[str, Any] = {
        "work_id": work_id,
        "lifecycle": {"state": state.get("state"), "phase": state.get("phase"), "updated_at": state.get("updated_at")},
        "delivery_authority": delivery,
        "attempt": None,
        "compatibility_diagnostics": [],
    }
    artifact_rel = delivery.get("delivery_artifact_dir") if delivery else None
    delivery_dir = run_dir / artifact_rel if isinstance(artifact_rel, str) else run_dir / "delivery"
    if not delivery_dir.resolve().is_relative_to(run_dir.resolve()):
        raise ContractError("delivery artifact directory is outside the run")
    contract_view: dict[str, Any] = {}
    for name, filename, version_key in (
        ("shaper", "shaper-contract.json", "version"),
        ("charter", "delivery-charter.json", "charter_version"),
    ):
        path = delivery_dir / filename
        if path.is_file() and not path.is_symlink():
            try:
                record = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                result["compatibility_diagnostics"].append({
                    "code": f"{name}_contract_unreadable", "severity": "error",
                    "message": f"{filename} is not readable JSON",
                })
            else:
                contract_view[name] = {
                    "id": record.get("shaper_contract_id") if name == "shaper" else record.get("charter_id"),
                    "version": record.get(version_key), "digest": record.get("digest"),
                    "approved_sources": record.get("approved_sources"),
                }
    result["contracts"] = contract_view
    execution_dir = run_dir / "execution"
    if attempt_id is None and execution_dir.is_dir() and not execution_dir.is_symlink():
        candidates = [path for path in execution_dir.iterdir()
                      if path.is_dir() and not path.is_symlink() and (path / "envelope.json").is_file()]
        if candidates:
            attempt_id = max(candidates, key=lambda path: path.stat().st_mtime_ns).name
    if attempt_id is None:
        return result
    if not attempt_id or any(char not in "0123456789abcdef" for char in attempt_id):
        raise ContractError("delivery attempt id is invalid")
    attempt_dir = execution_dir / attempt_id
    envelope_path = attempt_dir / "envelope.json"
    if not envelope_path.is_file() or envelope_path.is_symlink():
        raise ContractError("delivery attempt envelope is absent")
    raw = envelope_path.read_bytes()
    try:
        envelope = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        legacy = inspect_legacy_delivery(raw)
        result["attempt"] = legacy
        result["compatibility_diagnostics"] = legacy["diagnostics"]
        return result
    protocol = envelope.get("execution_protocol_version") if isinstance(envelope, dict) else None
    if protocol == 6:
        legacy = inspect_legacy_delivery(raw)
        result["attempt"] = legacy
        result["compatibility_diagnostics"] = legacy["diagnostics"]
        return result
    if protocol not in {DELIVERY_PROTOCOL_VERSION, STRUCTURED_VERIFIER_PROTOCOL_VERSION}:
        result["attempt"] = {
            "execution_protocol_version": protocol,
            "readable": True,
            "executable": False,
            "resumable": False,
        }
        result["compatibility_diagnostics"] = [{
            "code": "unsupported_delivery_protocol",
            "severity": "warning",
            "message": f"execution protocol v{protocol} is outside Delivery inspection support",
        }]
        return result
    ledger_path = execution_dir / "ledger.sqlite"
    if not ledger_path.is_file() or ledger_path.is_symlink():
        raise ContractError("delivery execution ledger is absent")
    snapshot = ExecutionLedger(ledger_path, read_only=True).snapshot(attempt_id)
    if protocol == STRUCTURED_VERIFIER_PROTOCOL_VERSION:
        receipt_path = attempt_dir / "receipt.json"
        receipt_file = None
        if receipt_path.is_file() and not receipt_path.is_symlink():
            raw_receipt = receipt_path.read_bytes()
            try:
                present = "recovery" in json.loads(raw_receipt)
            except (UnicodeDecodeError, json.JSONDecodeError):
                present = None
            receipt_file = {"sha256": hashlib.sha256(raw_receipt).hexdigest(), "recovery_block_present": present}
        attempt = inspect_delivery_projection(envelope, snapshot, lead_active=lead_claim_active(delivery, envelope),
                                              receipt_file=receipt_file)
    else:
        attempt = inspect_delivery_projection(envelope, snapshot)
    attempt["pending_unknowns"] = [
        item.get("action_id") or item.get("call_id")
        for item in snapshot.get("actions", []) + snapshot.get("manager_calls", [])
        if item.get("status") in {"started", "unknown"}
    ]
    attempt["pending_approvals"] = [
        item.get("action_id") or item.get("call_id")
        for item in snapshot.get("actions", []) + snapshot.get("manager_calls", [])
        if item.get("status") in {"proposed", "pending_approval"}
    ]
    result["attempt"] = attempt
    return result
