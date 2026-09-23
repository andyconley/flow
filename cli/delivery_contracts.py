"""Canonical Flow contracts for the Shaper-to-Delivery boundary.

These records are runtime-neutral authority. Providers and MAF receive a later
projection and cannot add fields to these sealed artifacts.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA_VERSION = 1
SHAPER_CONTRACT_VERSION = 1
DELIVERY_CHARTER_VERSION = 1


class DeliveryContractError(ValueError):
    pass


def canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DeliveryContractError(f"record is not canonical JSON: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeliveryContractError(f"{field} must be a non-empty string")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise DeliveryContractError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _list(value: object, field: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        raise DeliveryContractError(f"{field} must be {'a non-empty ' if nonempty else 'a '}list")
    return value


def _mapping(value: object, field: str, *, keys: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or (keys is not None and set(value) != keys):
        raise DeliveryContractError(f"{field} is invalid")
    return value


def _sources(sources: object, work_id: str) -> dict[str, dict[str, str]]:
    sources = _mapping(sources, "approved_sources")
    required = {"requirements", "acceptance_criteria"}
    if not required.issubset(sources):
        raise DeliveryContractError("approved_sources must include requirements and acceptance_criteria")
    prefix = f".flow/runs/{work_id}/"
    normalized: dict[str, dict[str, str]] = {}
    for name, source in sorted(sources.items()):
        source = _mapping(source, f"source {name}", keys={"path", "sha256"})
        path = _text(source["path"], f"source {name} path")
        if not path.startswith(prefix) or any(part in {"", ".", ".."} for part in path.split("/")):
            raise DeliveryContractError(f"source {name} path is outside the current run")
        normalized[name] = {"path": path, "sha256": _sha(source["sha256"], f"source {name} sha256")}
    return normalized


def _claim(value: str, sources: dict[str, dict[str, str]]) -> dict[str, Any]:
    return {"value": value, "provenance": [{"source": name, "sha256": source["sha256"], "claim_status": "approved"} for name, source in sorted(sources.items())]}


INTENT_FIELDS = {
    "problem", "intended_users", "outcomes", "scope", "exclusions", "constraints",
    "assumptions", "acceptance_criteria", "risks", "open_decisions", "decision_owners",
    "allowed_specialists", "prohibited_capabilities", "delegation_matrix", "approval_matrix",
    "budget_safety_envelope", "boundaries", "amendment_lineage", "approval_history",
    "next_lane_eligibility",
}


def validate_shaper_intent(intent: object) -> dict[str, Any]:
    intent = _mapping(intent, "shaper_intent", keys=INTENT_FIELDS)
    _text(intent["problem"], "problem")
    for name in ("intended_users", "outcomes", "scope", "exclusions", "constraints", "assumptions", "acceptance_criteria"):
        values = _list(intent[name], name, nonempty=True)
        for value in values:
            _text(value, name)
    for name in ("risks", "open_decisions", "decision_owners", "allowed_specialists", "prohibited_capabilities", "amendment_lineage", "approval_history", "next_lane_eligibility"):
        _list(intent[name], name, nonempty=name in {"risks", "allowed_specialists", "prohibited_capabilities", "approval_history", "next_lane_eligibility"})
    for name in ("delegation_matrix", "approval_matrix", "budget_safety_envelope", "boundaries"):
        _mapping(intent[name], name)
    for specialist in intent["allowed_specialists"]:
        specialist = _mapping(specialist, "allowed specialist", keys={"role", "capabilities", "definition_digest"})
        _text(specialist["role"], "allowed specialist role")
        _list(specialist["capabilities"], "allowed specialist capabilities", nonempty=True)
        _sha(specialist["definition_digest"], "allowed specialist definition_digest")
    if intent["delegation_matrix"].get("delegated_expansion") is not False:
        raise DeliveryContractError("delegated expansion must remain explicitly disabled")
    if intent["approval_matrix"].get("provider_dispatch") != "Flow_grant":
        raise DeliveryContractError("provider dispatch must require a Flow grant")
    return intent


def _intent(work_id: str, sources: dict[str, dict[str, str]], approved: dict[str, Any]) -> dict[str, Any]:
    """Project a reviewed per-run intent artifact without guessing Markdown semantics."""
    approved = validate_shaper_intent(approved)
    claimed = lambda value: _claim(value, sources)
    return {
        "problem": claimed(approved["problem"]),
        **{name: [claimed(value) for value in approved[name]] for name in
           ("intended_users", "outcomes", "scope", "exclusions", "constraints", "assumptions", "acceptance_criteria")},
        "source_evidence": [{"source": name, "sha256": source["sha256"], "claim_status": "approved", "provenance": source["path"]} for name, source in sorted(sources.items())],
        **{name: approved[name] for name in ("risks", "open_decisions", "decision_owners", "allowed_specialists",
           "prohibited_capabilities", "delegation_matrix", "approval_matrix", "budget_safety_envelope",
           "boundaries", "amendment_lineage", "approval_history", "next_lane_eligibility")},
    }


def _seal(record: dict[str, Any], validator) -> dict[str, Any]:
    result = dict(record)
    result["digest"] = digest(result)
    validator(result)
    return result


def build_shaper_contract(work_id: str, sources: dict[str, dict[str, str]], intent: dict[str, Any], *, approval_event: str = "approve-definition") -> dict[str, Any]:
    work_id = _text(work_id, "run_id")
    sources = _sources(sources, work_id)
    intent = _intent(work_id, sources, intent)
    record = {
        "schema_version": SCHEMA_VERSION, "version": SHAPER_CONTRACT_VERSION, "kind": "shaper_contract",
        "shaper_contract_id": f"shaper-{digest({'run_id': work_id, 'sources': sources})[:20]}",
        "run_id": work_id, "status": "approved", "approved_sources": sources,
        "approval_event": _text(approval_event, "approval_event"), **intent,
    }
    return _seal(record, validate_shaper_contract)


def build_delivery_charter(shaper: dict[str, Any]) -> dict[str, Any]:
    validate_shaper_contract(shaper)
    charter_id = f"delivery-{digest({'shaper': shaper['digest']})[:20]}"
    definitions = {item["role"]: {"definition_digest": item["definition_digest"], "maximum_instances": 1} for item in shaper["allowed_specialists"]}
    record = {
        "schema_version": SCHEMA_VERSION, "charter_version": DELIVERY_CHARTER_VERSION, "kind": "delivery_charter",
        "charter_id": charter_id, "run_id": shaper["run_id"], "delivery_attempt_policy": {"one_active_lead": True, "resume_or_supersede": "explicit"},
        "shaper_contract": {"id": shaper["shaper_contract_id"], "version": shaper["version"], "digest": shaper["digest"]},
        "approved_sources": shaper["approved_sources"], "outcomes": shaper["outcomes"], "scope": shaper["scope"],
        "exclusions": shaper["exclusions"], "constraints": shaper["constraints"], "acceptance_criteria": shaper["acceptance_criteria"],
        "accepted_risks": shaper["risks"], "eligible_specialists": definitions,
        "provider_capabilities": {"claude": {"binding": "capability"}, "codex": {"binding": "capability"}, "ollama": {"binding": "verifier"}},
        "limits": {"delegations": 6, "concurrency": 3, "replans": 2, "runtime_seconds": 300, "tools": ["read", "edit", "test"], "paths": ["charter-scoped"], "outputs": ["diff", "test", "receipt"], "retries": 0},
        "approval_matrix": shaper["approval_matrix"], "producer_verifier_rules": {"distinct_identities": True, "verifier_read_only": True},
        "validation": {"flow_observed_diff_and_test_before_verifier": True}, "recovery": {"unknown_action_blocks_successor": True, "takeover": "explicit_resume_or_supersede"},
        "escalation_stop_cancellation": {"scope_expansion": "halt_for_shaper", "cancellation": "Flow_only"},
        "boundaries": shaper["boundaries"], "handback": ["receipt", "diff", "test", "verifier_evidence"],
        "approver": {"identity": "engineer", "event": shaper["approval_event"]}, "amendment_lineage": shaper["amendment_lineage"], "compatibility_version": 7,
    }
    return _seal(record, validate_delivery_charter)


def _validate_digest(record: dict[str, Any], label: str) -> None:
    expected = dict(record)
    actual = expected.pop("digest", None)
    if _sha(actual, f"{label} digest") != digest(expected):
        raise DeliveryContractError(f"{label} digest mismatch")


def validate_shaper_contract(record: dict[str, Any]) -> None:
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION or record.get("version") != SHAPER_CONTRACT_VERSION or record.get("kind") != "shaper_contract":
        raise DeliveryContractError("unsupported Shaper Contract version")
    work_id = _text(record.get("run_id"), "run_id")
    _text(record.get("shaper_contract_id"), "shaper_contract_id")
    if record.get("status") != "approved":
        raise DeliveryContractError("Shaper Contract must be approved")
    _sources(record.get("approved_sources"), work_id)
    _text(record.get("approval_event"), "approval_event")
    required_lists = ("intended_users", "outcomes", "scope", "exclusions", "constraints", "assumptions", "acceptance_criteria", "source_evidence", "risks", "open_decisions", "decision_owners", "allowed_specialists", "prohibited_capabilities", "amendment_lineage", "approval_history", "next_lane_eligibility")
    _mapping(record.get("problem"), "problem", keys={"value", "provenance"})
    for name in required_lists:
        _list(record.get(name), name, nonempty=name not in {"open_decisions", "decision_owners", "amendment_lineage"})
    for name in ("delegation_matrix", "approval_matrix", "budget_safety_envelope", "boundaries"):
        _mapping(record.get(name), name)
    if record["delegation_matrix"].get("delegated_expansion") is not False:
        raise DeliveryContractError("delegated expansion must remain explicitly disabled")
    if record["approval_matrix"].get("provider_dispatch") != "Flow_grant":
        raise DeliveryContractError("provider dispatch must require a Flow grant")
    _validate_digest(record, "Shaper Contract")


def validate_delivery_charter(record: dict[str, Any]) -> None:
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION or record.get("charter_version") != DELIVERY_CHARTER_VERSION or record.get("kind") != "delivery_charter":
        raise DeliveryContractError("unsupported Delivery Charter version")
    work_id = _text(record.get("run_id"), "run_id")
    _text(record.get("charter_id"), "charter_id")
    _sources(record.get("approved_sources"), work_id)
    _mapping(record.get("delivery_attempt_policy"), "delivery_attempt_policy", keys={"one_active_lead", "resume_or_supersede"})
    if record["delivery_attempt_policy"] != {"one_active_lead": True, "resume_or_supersede": "explicit"}:
        raise DeliveryContractError("Delivery Charter attempt policy is invalid")
    source = _mapping(record.get("shaper_contract"), "shaper_contract", keys={"id", "version", "digest"})
    _text(source["id"], "shaper_contract id")
    if source["version"] != SHAPER_CONTRACT_VERSION:
        raise DeliveryContractError("shaper_contract version is invalid")
    _sha(source["digest"], "shaper_contract digest")
    for name in ("outcomes", "scope", "exclusions", "constraints", "acceptance_criteria", "accepted_risks", "handback", "amendment_lineage"):
        _list(record.get(name), name, nonempty=name != "amendment_lineage")
    _mapping(record.get("eligible_specialists"), "eligible_specialists")
    for role, definition in record["eligible_specialists"].items():
        _text(role, "eligible specialist role")
        definition = _mapping(definition, "eligible specialist", keys={"definition_digest", "maximum_instances"})
        _sha(definition["definition_digest"], "specialist definition digest")
        if not isinstance(definition["maximum_instances"], int) or definition["maximum_instances"] < 1:
            raise DeliveryContractError("maximum_instances is invalid")
    _mapping(record.get("provider_capabilities"), "provider_capabilities")
    limits = _mapping(record.get("limits"), "limits", keys={"delegations", "concurrency", "replans", "runtime_seconds", "tools", "paths", "outputs", "retries"})
    if not all(isinstance(limits[key], int) and limits[key] >= 0 for key in ("delegations", "concurrency", "replans", "runtime_seconds", "retries")):
        raise DeliveryContractError("Delivery Charter numeric limits are invalid")
    for name in ("approval_matrix", "producer_verifier_rules", "validation", "recovery", "escalation_stop_cancellation", "boundaries", "approver"):
        _mapping(record.get(name), name)
    if record["approval_matrix"].get("provider_dispatch") != "Flow_grant":
        raise DeliveryContractError("provider dispatch must require a Flow grant")
    if record["compatibility_version"] != 7:
        raise DeliveryContractError("Delivery Charter compatibility version is invalid")
    _validate_digest(record, "Delivery Charter")
