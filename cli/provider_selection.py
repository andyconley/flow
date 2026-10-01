"""Pure, canonical deterministic provider selection.

This module performs no I/O and grants no authority. Flow and the supervised
MAF child call the same functions over sealed inputs; Flow grants dispatch only
when their canonical decisions match.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable


SELECTOR_VERSION = "provider-selector-v1"
PROVIDERS = ("ollama", "claude", "codex")
TIER_RANK = {"mechanical": 0, "working": 1, "judgment": 2, "demanding": 3}
LOCALITY_RANK = {"local_required": 2, "local_preferred": 1, "any": 0}
EXCLUSION_CODES = frozenset({
    "candidate_not_allowed", "candidate_disabled", "operation_unsupported",
    "tier_insufficient", "capability_missing", "privacy_incompatible",
    "input_limit_exceeded", "output_limit_exceeded", "context_limit_exceeded",
    "cost_class_exceeded", "availability_unavailable", "availability_unknown",
    "availability_stale", "prior_no_send_failure", "provider_family_conflict",
})


class SelectionPolicyError(ValueError):
    """Raised when policy or selection inputs violate the contract."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def merge_selection_policy(
    framework: dict[str, Any],
    administrator: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge policy with monotonic safety and field provenance.

    Allowlists intersect, disabled candidates union, ceilings take the minimum,
    and lower layers may only reorder surviving providers. Run-local policy may
    additionally carry an explicitly approved independence waiver.
    """
    layers = [("framework", framework), ("administrator", administrator or {}),
              ("project", project or {}), ("run", run or {})]
    effective = {
        "schema_version": 1,
        "allowed_candidates": None,
        "disabled_candidates": [],
        "provider_order": list(PROVIDERS),
        "candidate_priority": [],
        "max_cost_class": None,
        "max_input_bytes": None,
        "max_output_bytes": None,
        "max_context_tokens": None,
        "independence_waiver": None,
        "provenance": {},
    }
    allowed: set[str] | None = None
    disabled: set[str] = set()
    for layer_name, layer in layers:
        if not isinstance(layer, dict):
            raise SelectionPolicyError(f"{layer_name} selection policy must be a mapping")
        unknown = set(layer) - {
            "allowed_candidates", "disabled_candidates", "provider_order", "candidate_priority", "max_cost_class",
            "max_input_bytes", "max_output_bytes", "max_context_tokens", "independence_waiver",
        }
        if unknown:
            raise SelectionPolicyError(f"unknown {layer_name} policy fields: {', '.join(sorted(unknown))}")
        if "allowed_candidates" in layer:
            values = _strings(layer["allowed_candidates"], f"{layer_name}.allowed_candidates")
            allowed = set(values) if allowed is None else allowed & set(values)
            effective["provenance"].setdefault("allowed_candidates", []).append(layer_name)
        if "disabled_candidates" in layer:
            disabled.update(_strings(layer["disabled_candidates"], f"{layer_name}.disabled_candidates"))
            effective["provenance"].setdefault("disabled_candidates", []).append(layer_name)
        if "provider_order" in layer:
            order = _strings(layer["provider_order"], f"{layer_name}.provider_order")
            if set(order) != set(PROVIDERS) or len(order) != len(PROVIDERS):
                raise SelectionPolicyError("provider_order must contain ollama, claude, and codex once")
            # Local-first is an invariant. Lower layers tune hosted ordering only.
            if order[0] != "ollama":
                raise SelectionPolicyError("provider_order must keep ollama first")
            effective["provider_order"] = order
            effective["provenance"]["provider_order"] = layer_name
        if "candidate_priority" in layer:
            priority = _strings(layer["candidate_priority"], f"{layer_name}.candidate_priority")
            if len(set(priority)) != len(priority):
                raise SelectionPolicyError("candidate_priority must contain unique candidate IDs")
            effective["candidate_priority"] = priority
            effective["provenance"]["candidate_priority"] = layer_name
        for field in ("max_cost_class", "max_input_bytes", "max_output_bytes", "max_context_tokens"):
            if field not in layer:
                continue
            value = layer[field]
            if not isinstance(value, int) or value < 0:
                raise SelectionPolicyError(f"{layer_name}.{field} must be a non-negative integer")
            prior = effective[field]
            effective[field] = value if prior is None else min(prior, value)
            effective["provenance"].setdefault(field, []).append(layer_name)
        if "independence_waiver" in layer:
            if layer_name != "run":
                raise SelectionPolicyError("independence waiver is run-local only")
            waiver = layer["independence_waiver"]
            _validate_waiver_shape(waiver)
            effective["independence_waiver"] = deepcopy(waiver)
            effective["provenance"]["independence_waiver"] = "run"
    effective["allowed_candidates"] = sorted(allowed) if allowed is not None else None
    effective["disabled_candidates"] = sorted(disabled)
    effective["policy_digest"] = digest({key: value for key, value in effective.items() if key != "policy_digest"})
    return effective


def select_candidate(
    requirements: dict[str, Any], policy: dict[str, Any], catalog: Iterable[dict[str, Any]],
    availability: Iterable[dict[str, Any]], *, prior_no_send_failures: Iterable[str] = (),
    excluded_families: Iterable[str] = (),
) -> dict[str, Any]:
    """Select the first eligible candidate using a total deterministic order."""
    candidates = sorted((deepcopy(item) for item in catalog), key=lambda item: item.get("candidate_id", ""))
    readiness = {item.get("candidate_id"): item for item in availability}
    failure_history = list(prior_no_send_failures)
    if (any(not isinstance(item, str) or not item for item in failure_history)
            or len(set(failure_history)) != len(failure_history)):
        raise SelectionPolicyError("prior_no_send_failures must contain unique nonblank candidate IDs")
    failures = set(failure_history)
    family_exclusions = set(excluded_families)
    provider_order = policy.get("provider_order", list(PROVIDERS))
    provider_rank = {provider: index for index, provider in enumerate(provider_order)}
    configured_priority = policy.get("candidate_priority", [])
    if (not isinstance(configured_priority, list)
            or any(not isinstance(item, str) or not item for item in configured_priority)
            or len(set(configured_priority)) != len(configured_priority)):
        raise SelectionPolicyError("candidate_priority must contain unique nonblank candidate IDs")
    candidate_rank = {candidate_id: index for index, candidate_id in enumerate(configured_priority)}
    allowed = policy.get("allowed_candidates")
    disabled = set(policy.get("disabled_candidates", []))
    exclusions: list[dict[str, Any]] = []
    eligible: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in seen:
            raise SelectionPolicyError("catalog candidate_id values must be unique and nonblank")
        seen.add(candidate_id)
        reasons = _candidate_exclusions(candidate, requirements, policy, readiness.get(candidate_id),
                                        allowed, disabled, failures, family_exclusions)
        if reasons:
            exclusions.append({"candidate_id": candidate_id, "reason_codes": sorted(reasons)})
            continue
        rank = (
            provider_rank.get(candidate.get("provider"), len(provider_rank)),
            TIER_RANK[candidate["tier"]] - TIER_RANK[requirements.get("minimum_tier", "mechanical")],
            candidate_rank.get(candidate_id, len(candidate_rank)),
            int(candidate.get("cost_class", 0)),
            candidate_id,
        )
        eligible.append((rank, candidate))
    eligible.sort(key=lambda item: item[0])
    ordered = [{"candidate_id": item[1]["candidate_id"], "rank_tuple": list(item[0])} for item in eligible]
    selected = deepcopy(eligible[0][1]) if eligible else None
    decision = {
        "schema_version": 1,
        "selector_version": SELECTOR_VERSION,
        "requirements_digest": digest(requirements),
        "policy_digest": policy.get("policy_digest") or digest(policy),
        "catalog_digest": digest(candidates),
        "availability_digest": digest(sorted(readiness.values(), key=lambda item: item.get("candidate_id", ""))),
        "prior_no_send_failures": failure_history,
        "excluded_families": sorted(family_exclusions),
        "exclusions": exclusions,
        "ordered_candidates": ordered,
        "selected_candidate_id": selected.get("candidate_id") if selected else None,
        "selected_binding": ({key: selected.get(key) for key in ("candidate_id", "provider", "model", "provider_family")}
                             if selected else None),
    }
    decision["decision_digest"] = digest(decision)
    return decision


def _candidate_exclusions(candidate: dict[str, Any], requirements: dict[str, Any], policy: dict[str, Any],
                          availability: dict[str, Any] | None, allowed: list[str] | None,
                          disabled: set[str], failures: set[str], family_exclusions: set[str]) -> set[str]:
    candidate_id = candidate["candidate_id"]
    reasons: set[str] = set()
    if allowed is not None and candidate_id not in allowed:
        reasons.add("candidate_not_allowed")
    if candidate_id in disabled or candidate.get("enabled") is False:
        reasons.add("candidate_disabled")
    if requirements.get("operation") not in candidate.get("operations", []):
        reasons.add("operation_unsupported")
    if TIER_RANK.get(candidate.get("tier"), -1) < TIER_RANK.get(requirements.get("minimum_tier"), 0):
        reasons.add("tier_insufficient")
    if not set(requirements.get("required_capabilities", [])).issubset(candidate.get("capabilities", [])):
        reasons.add("capability_missing")
    locality = requirements.get("locality", "any")
    if LOCALITY_RANK.get(locality, 0) >= LOCALITY_RANK["local_required"] and candidate.get("locality") != "local":
        reasons.add("privacy_incompatible")
    for req_field, candidate_field, policy_field, code in (
        ("input_bytes", "max_input_bytes", "max_input_bytes", "input_limit_exceeded"),
        ("output_bytes", "max_output_bytes", "max_output_bytes", "output_limit_exceeded"),
        ("context_tokens", "max_context_tokens", "max_context_tokens", "context_limit_exceeded"),
    ):
        needed = requirements.get(req_field, 0)
        ceilings = [value for value in (candidate.get(candidate_field), policy.get(policy_field)) if value is not None]
        if ceilings and needed > min(ceilings):
            reasons.add(code)
    if policy.get("max_cost_class") is not None and candidate.get("cost_class", 0) > policy["max_cost_class"]:
        reasons.add("cost_class_exceeded")
    state = availability.get("state") if availability else "unknown"
    if state != "ready":
        reasons.add(f"availability_{state}" if state in {"unavailable", "unknown", "stale"} else "availability_unknown")
    if candidate_id in failures:
        reasons.add("prior_no_send_failure")
    if candidate.get("provider_family") in family_exclusions:
        reasons.add("provider_family_conflict")
    if not reasons.issubset(EXCLUSION_CODES):
        raise SelectionPolicyError("selector produced an uncontrolled exclusion")
    return reasons


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise SelectionPolicyError(f"{field} must be an array of nonblank strings")
    return list(value)


def _validate_waiver_shape(waiver: Any) -> None:
    fields = {
        "schema_version", "decision", "work_id", "attempt_id", "assignment_id",
        "risk_class", "excluded_provider_families", "waived_provider_families",
        "prior_policy_digest", "successor_authority_digest", "approval_actor",
        "approval_event_digest", "approval_digest",
    }
    if not isinstance(waiver, dict) or set(waiver) != fields:
        raise SelectionPolicyError("independence waiver requires a closed sealed approval")
    if (waiver["schema_version"] != 1 or waiver["decision"] != "approve"
            or waiver["risk_class"] != "high" or waiver["approval_actor"] != "user"):
        raise SelectionPolicyError("independence waiver requires explicit scoped user approval")
    for field in ("work_id", "attempt_id", "assignment_id"):
        if not isinstance(waiver[field], str) or not waiver[field]:
            raise SelectionPolicyError(f"independence waiver {field} must be nonblank")
    excluded = _strings(waiver["excluded_provider_families"], "excluded_provider_families")
    waived = _strings(waiver["waived_provider_families"], "waived_provider_families")
    if len(set(excluded)) != len(excluded) or len(set(waived)) != len(waived) or not waived or not set(waived).issubset(excluded):
        raise SelectionPolicyError("independence waiver family scope is invalid")
    for field in ("prior_policy_digest", "successor_authority_digest", "approval_event_digest", "approval_digest"):
        value = waiver[field]
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise SelectionPolicyError(f"independence waiver {field} must be a sha256 digest")
    if waiver["approval_digest"] != digest({key: value for key, value in waiver.items() if key != "approval_digest"}):
        raise SelectionPolicyError("independence waiver approval digest mismatch")
