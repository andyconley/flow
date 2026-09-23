"""Read-only view of a Flow v7 Delivery Lead projection.

The CLI layer uses this module rather than reconstructing authority from a
receipt.  A v7 execution record remains executable only while its attempt is
started and its current owner generation matches the embedded lead claim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from execution_contracts import ContractError, DELIVERY_PROTOCOL_VERSION, validate_envelope
from execution_ledger import ExecutionLedger
from fsutil import repo_root
from legacy_delivery import inspect_legacy_delivery


def inspect_delivery_projection(envelope: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, non-authorizing v7 delivery-inspection view.

    ``snapshot`` is the ledger's current snapshot. This function intentionally
    does not grant, recover, or mutate anything.
    """
    validate_envelope(envelope)
    if envelope.get("execution_protocol_version") != DELIVERY_PROTOCOL_VERSION:
        raise ContractError("delivery inspection requires execution protocol v7")
    if snapshot.get("attempt_id") != envelope["attempt_id"]:
        raise ContractError("delivery inspection attempt differs from projection")
    claim = envelope["delivery_lead_claim"]
    current_generation = snapshot.get("owner_generation")
    status = snapshot.get("status")
    active = status == "started" and current_generation == claim["generation"]
    return {
        "execution_protocol_version": DELIVERY_PROTOCOL_VERSION,
        "work_id": envelope["work_id"],
        "attempt_id": envelope["attempt_id"],
        "status": status,
        "executable": active,
        "resumable": active,
        "delivery_lead": {"id": claim["lead_id"], "generation": claim["generation"],
                          "current_generation": current_generation, "active": active},
        "contracts": {field: envelope[field] for field in ("shaper_contract_digest", "delivery_charter_digest", "handoff_digest", "delivery_lead_claim_digest")},
        "provider_choices": [item["request"]["provider_choice"] for item in snapshot.get("actions", [])
                             if isinstance(item, dict) and isinstance(item.get("request"), dict)
                             and "provider_choice" in item["request"]],
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
    if protocol != DELIVERY_PROTOCOL_VERSION:
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
