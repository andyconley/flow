"""Closed Flow authority for protocol-v9 provider selection.

The selector remains a pure function.  This module is the trust boundary that
admits only normalized, credential-free inputs and binds narrowly scoped user
amendments to one successor authority generation.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from provider_selection import LOCALITY_RANK, PROVIDERS, TIER_RANK, digest
except ModuleNotFoundError:  # Package import used by the MAF child.
    from .provider_selection import LOCALITY_RANK, PROVIDERS, TIER_RANK, digest


OPERATIONS = frozenset({"manage", "read", "edit", "verify", "collect"})
CAPABILITIES = frozenset({"structured_output", "structured_edit", "evidence_collection"})
RISK_CLASSES = frozenset({"standard", "high"})
AVAILABILITY_STATES = frozenset({"ready", "unavailable", "unknown", "stale"})
AVAILABILITY_EVIDENCE_CODES = frozenset({
    "model_present", "adapter_ready", "authentication_ready",
    "model_absent", "adapter_unavailable", "authentication_unavailable",
    "probe_failed", "observation_expired",
})
AVAILABILITY_EVIDENCE_BY_STATE = {
    "ready": frozenset({"model_present", "adapter_ready", "authentication_ready"}),
    "unavailable": frozenset({"model_absent", "adapter_unavailable", "authentication_unavailable"}),
    "unknown": frozenset({"probe_failed"}),
    "stale": frozenset({"observation_expired"}),
}
MAX_AVAILABILITY_TTL = timedelta(minutes=5)
MAX_FUTURE_SKEW = timedelta(seconds=30)


class SelectionAuthorityError(ValueError):
    """A v9 selection input is malformed, unsealed, or out of scope."""


def _closed(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise SelectionAuthorityError(f"{label} fields are invalid")
    return value


def _nonblank(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SelectionAuthorityError(f"{label} must be nonblank")
    return value


def _hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise SelectionAuthorityError(f"{label} must be a sha256 digest")
    return value


def _unique_strings(value: Any, label: str, *, allowed: frozenset[str] | None = None) -> list[str]:
    if (not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value)
            or len(set(value)) != len(value)):
        raise SelectionAuthorityError(f"{label} must contain unique nonblank strings")
    if allowed is not None and not set(value).issubset(allowed):
        raise SelectionAuthorityError(f"{label} contains an unsupported value")
    return value


def _uint(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SelectionAuthorityError(f"{label} must be a non-negative integer")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SelectionAuthorityError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SelectionAuthorityError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise SelectionAuthorityError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_requirements(requirements: Any) -> None:
    required = {
        "operation", "minimum_tier", "required_capabilities", "locality",
        "input_bytes", "output_bytes", "context_tokens", "risk_class",
        "independence_required",
    }
    value = _closed(requirements, required, "logical requirements")
    if value["operation"] not in OPERATIONS:
        raise SelectionAuthorityError("logical requirements operation is unsupported")
    if value["minimum_tier"] not in TIER_RANK:
        raise SelectionAuthorityError("logical requirements minimum_tier is unsupported")
    _unique_strings(value["required_capabilities"], "logical requirements capabilities", allowed=CAPABILITIES)
    if value["locality"] not in LOCALITY_RANK:
        raise SelectionAuthorityError("logical requirements locality is unsupported")
    for field in ("input_bytes", "output_bytes", "context_tokens"):
        _uint(value[field], f"logical requirements {field}")
    if value["risk_class"] not in RISK_CLASSES:
        raise SelectionAuthorityError("logical requirements risk_class is unsupported")
    if type(value["independence_required"]) is not bool:
        raise SelectionAuthorityError("logical requirements independence_required must be boolean")
    if value["independence_required"] and value["operation"] != "verify":
        raise SelectionAuthorityError("provider-family independence is valid only for verification")


def validate_effective_policy(policy: Any) -> None:
    fields = {
        "schema_version", "allowed_candidates", "disabled_candidates", "provider_order", "candidate_priority",
        "max_cost_class", "max_input_bytes", "max_output_bytes", "max_context_tokens",
        "independence_waiver", "provenance", "policy_digest",
    }
    value = _closed(policy, fields, "effective selection policy")
    if value["schema_version"] != 1:
        raise SelectionAuthorityError("effective selection policy schema is unsupported")
    if value["allowed_candidates"] is not None:
        _unique_strings(value["allowed_candidates"], "allowed_candidates")
    _unique_strings(value["disabled_candidates"], "disabled_candidates")
    order = _unique_strings(value["provider_order"], "provider_order", allowed=frozenset(PROVIDERS))
    if tuple(order) not in (("ollama", "claude", "codex"), ("ollama", "codex", "claude")):
        raise SelectionAuthorityError("provider_order must keep Ollama first and contain each provider once")
    _unique_strings(value["candidate_priority"], "candidate_priority")
    for field in ("max_cost_class", "max_input_bytes", "max_output_bytes", "max_context_tokens"):
        if value[field] is not None:
            _uint(value[field], field)
    if not isinstance(value["provenance"], dict) or not set(value["provenance"]).issubset(fields - {"provenance", "policy_digest"}):
        raise SelectionAuthorityError("effective selection policy provenance is invalid")
    layers = frozenset({"framework", "administrator", "project", "run"})
    for field, source in value["provenance"].items():
        if field in {"provider_order", "candidate_priority", "independence_waiver"}:
            if source not in layers:
                raise SelectionAuthorityError("effective selection policy provenance source is invalid")
        elif (not isinstance(source, list) or not source or len(set(source)) != len(source)
              or not set(source).issubset(layers)):
            raise SelectionAuthorityError("effective selection policy provenance sources are invalid")
    if value["independence_waiver"] is not None and value["provenance"].get("independence_waiver") != "run":
        raise SelectionAuthorityError("independence waiver provenance must be run-local")
    if value["independence_waiver"] is not None:
        validate_independence_waiver(value["independence_waiver"])
    expected = digest({key: item for key, item in value.items() if key != "policy_digest"})
    if value["policy_digest"] != expected:
        raise SelectionAuthorityError("effective selection policy digest mismatch")


def validate_catalog(catalog: Any) -> None:
    if not isinstance(catalog, list) or not catalog:
        raise SelectionAuthorityError("candidate catalog must be a nonempty array")
    allowed_fields = {
        "candidate_id", "provider", "model", "provider_family", "tier", "locality",
        "operations", "capabilities", "cost_class", "enabled", "max_input_bytes",
        "max_output_bytes", "max_context_tokens",
    }
    required_fields = allowed_fields - {"max_input_bytes", "max_output_bytes", "max_context_tokens"}
    seen: set[str] = set()
    for candidate in catalog:
        if not isinstance(candidate, dict) or not required_fields.issubset(candidate) or not set(candidate).issubset(allowed_fields):
            raise SelectionAuthorityError("candidate catalog fields are invalid")
        candidate_id = _nonblank(candidate["candidate_id"], "candidate_id")
        if candidate_id in seen:
            raise SelectionAuthorityError("candidate catalog identities must be unique")
        seen.add(candidate_id)
        if candidate["provider"] not in PROVIDERS:
            raise SelectionAuthorityError("candidate provider is unsupported")
        _nonblank(candidate["model"], "candidate model")
        _nonblank(candidate["provider_family"], "candidate provider_family")
        if candidate["tier"] not in TIER_RANK or candidate["locality"] not in {"local", "hosted"}:
            raise SelectionAuthorityError("candidate tier or locality is unsupported")
        _unique_strings(candidate["operations"], "candidate operations", allowed=OPERATIONS)
        _unique_strings(candidate["capabilities"], "candidate capabilities", allowed=CAPABILITIES)
        _uint(candidate["cost_class"], "candidate cost_class")
        if type(candidate["enabled"]) is not bool:
            raise SelectionAuthorityError("candidate enabled must be boolean")
        for field in ("max_input_bytes", "max_output_bytes", "max_context_tokens"):
            if field in candidate:
                _uint(candidate[field], f"candidate {field}")


def validate_availability_snapshot(availability: Any, *, sealed_at: str) -> None:
    if not isinstance(availability, list):
        raise SelectionAuthorityError("availability snapshot must be an array")
    seal_time = _timestamp(sealed_at, "selection authority sealed_at")
    fields = {
        "schema_version", "candidate_id", "state", "observed_at", "expires_at",
        "evidence_code", "probe_version",
    }
    seen: set[str] = set()
    for record in availability:
        value = _closed(record, fields, "availability record")
        if value["schema_version"] != 1:
            raise SelectionAuthorityError("availability schema is unsupported")
        candidate_id = _nonblank(value["candidate_id"], "availability candidate_id")
        if candidate_id in seen:
            raise SelectionAuthorityError("availability identities must be unique")
        seen.add(candidate_id)
        if value["state"] not in AVAILABILITY_STATES or value["evidence_code"] not in AVAILABILITY_EVIDENCE_CODES:
            raise SelectionAuthorityError("availability state or evidence code is unsupported")
        if value["evidence_code"] not in AVAILABILITY_EVIDENCE_BY_STATE[value["state"]]:
            raise SelectionAuthorityError("availability evidence contradicts state")
        if value["probe_version"] != "availability-v1":
            raise SelectionAuthorityError("availability probe_version is unsupported")
        observed = _timestamp(value["observed_at"], "availability observed_at")
        expires = _timestamp(value["expires_at"], "availability expires_at")
        if expires <= observed or expires - observed > MAX_AVAILABILITY_TTL:
            raise SelectionAuthorityError("availability freshness window is invalid")
        if observed > seal_time + MAX_FUTURE_SKEW:
            raise SelectionAuthorityError("availability observation is from the future")
        if value["state"] == "ready" and expires <= seal_time:
            raise SelectionAuthorityError("ready availability is stale at authority seal time")


def validate_independence_waiver(waiver: Any) -> None:
    fields = {
        "schema_version", "decision", "work_id", "attempt_id", "assignment_id",
        "risk_class", "excluded_provider_families", "waived_provider_families",
        "prior_policy_digest", "successor_authority_digest", "approval_actor",
        "approval_event_digest", "approval_digest",
    }
    value = _closed(waiver, fields, "independence waiver")
    if value["schema_version"] != 1 or value["decision"] != "approve" or value["risk_class"] != "high":
        raise SelectionAuthorityError("independence waiver decision or scope is invalid")
    for field in ("work_id", "attempt_id", "assignment_id"):
        _nonblank(value[field], f"independence waiver {field}")
    excluded = _unique_strings(value["excluded_provider_families"], "excluded provider families")
    waived = _unique_strings(value["waived_provider_families"], "waived provider families")
    if not waived or not set(waived).issubset(excluded):
        raise SelectionAuthorityError("waived provider families must narrowly subset excluded families")
    for field in ("prior_policy_digest", "successor_authority_digest", "approval_event_digest"):
        _hex(value[field], f"independence waiver {field}")
    if value["approval_actor"] != "user":
        raise SelectionAuthorityError("independence waiver requires explicit user approval")
    expected = digest({key: item for key, item in value.items() if key != "approval_digest"})
    if value["approval_digest"] != expected:
        raise SelectionAuthorityError("independence waiver approval digest mismatch")


def _resolve_waiver_approval(envelope: dict[str, Any], waiver: dict[str, Any]) -> None:
    """Resolve a waiver against the Flow-owned append-only run event store."""
    checkpoints = Path(envelope.get("checkpoint_dir", ""))
    try:
        attempt_dir = checkpoints.resolve(strict=False).parent
        execution_dir = attempt_dir.parent
        run_dir = execution_dir.parent
    except (OSError, RuntimeError) as exc:
        raise SelectionAuthorityError("independence waiver approval store is unavailable") from exc
    if (checkpoints.name != "checkpoints" or execution_dir.name != "execution"
            or run_dir.name != envelope.get("work_id")):
        raise SelectionAuthorityError("independence waiver approval store path is invalid")
    events_path = run_dir / "events.jsonl"
    try:
        lines = events_path.read_text().splitlines()
    except OSError as exc:
        raise SelectionAuthorityError("independence waiver approval store is unavailable") from exc
    matches: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SelectionAuthorityError("independence waiver approval store is invalid") from exc
        if digest(event) == waiver["approval_event_digest"]:
            matches.append(event)
    if len(matches) != 1:
        raise SelectionAuthorityError("independence waiver approval event was not uniquely resolved")
    scope = {key: value for key, value in waiver.items()
             if key not in {"approval_actor", "approval_event_digest", "approval_digest"}}
    expected = {
        "event": "approve-provider-family-waiver",
        "authority": "user",
        "explicit": True,
        "waiver_scope": scope,
    }
    event = matches[0]
    if not isinstance(event, dict) or {key: event.get(key) for key in expected} != expected \
            or set(event) != set(expected) | {"at"}:
        raise SelectionAuthorityError("independence waiver approval event scope is invalid")
    _timestamp(event.get("at"), "independence waiver approval event at")


def successor_authority_digest(
    *, work_id: str, attempt_id: str, charter_digest: str, manifest_digest: str,
    generation: int, sealed_at: str,
    logical_assignments: list[dict[str, Any]], catalog: list[dict[str, Any]],
    availability: list[dict[str, Any]], independence_constraints: list[dict[str, Any]],
    prior_authority_digest: str | None,
) -> str:
    """Digest immutable successor scope without the (possibly amended) policy."""
    return digest({
        "work_id": work_id,
        "attempt_id": attempt_id,
        "charter_digest": charter_digest,
        "manifest_digest": manifest_digest,
        "generation": generation,
        "sealed_at": sealed_at,
        "requirements_digests": {
            item["assignment_id"]: digest(item["requirements"]) for item in logical_assignments
        },
        "catalog_digest": digest(catalog),
        "availability_digest": digest(availability),
        "independence_constraints": independence_constraints,
        "prior_authority_digest": prior_authority_digest,
    })


def seal_selection_authority(
    *, work_id: str, attempt_id: str, charter_digest: str, manifest_digest: str,
    generation: int, sealed_at: str,
    logical_assignments: list[dict[str, Any]], policy: dict[str, Any], catalog: list[dict[str, Any]],
    availability: list[dict[str, Any]], independence_constraints: list[dict[str, Any]] | None = None,
    prior_authority_digest: str | None = None,
) -> dict[str, Any]:
    """Construct the canonical Flow-issued authority record after normalization."""
    constraints = deepcopy(independence_constraints or [])
    binding = successor_authority_digest(
        work_id=work_id, attempt_id=attempt_id, charter_digest=charter_digest,
        manifest_digest=manifest_digest, generation=generation, sealed_at=sealed_at,
        logical_assignments=logical_assignments, catalog=catalog, availability=availability,
        independence_constraints=constraints, prior_authority_digest=prior_authority_digest,
    )
    authority = {
        "schema_version": 1,
        "issuer": "flow",
        "work_id": work_id,
        "attempt_id": attempt_id,
        "charter_digest": charter_digest,
        "manifest_digest": manifest_digest,
        "generation": generation,
        "sealed_at": sealed_at,
        "requirements_digests": {
            item["assignment_id"]: digest(item["requirements"]) for item in logical_assignments
        },
        "policy_digest": policy["policy_digest"],
        "catalog_digest": digest(catalog),
        "availability_digest": digest(availability),
        "independence_constraints": constraints,
        "prior_authority_digest": prior_authority_digest,
        "successor_authority_digest": binding,
    }
    authority["authority_digest"] = digest(authority)
    return authority


def _validate_constraints(constraints: Any, assignment_ids: set[str]) -> None:
    if not isinstance(constraints, list):
        raise SelectionAuthorityError("independence constraints must be an array")
    fields = {
        "assignment_id", "risk_class", "excluded_provider_families",
        "producer_assignment_ids", "evidence_collector_assignment_ids", "source_binding_digests",
    }
    seen: set[str] = set()
    for constraint in constraints:
        value = _closed(constraint, fields, "independence constraint")
        assignment_id = _nonblank(value["assignment_id"], "independence assignment_id")
        if assignment_id not in assignment_ids or assignment_id in seen or value["risk_class"] != "high":
            raise SelectionAuthorityError("independence constraint scope is invalid")
        seen.add(assignment_id)
        _unique_strings(value["excluded_provider_families"], "excluded provider families")
        producers = _unique_strings(value["producer_assignment_ids"], "producer assignment ids")
        collectors = _unique_strings(value["evidence_collector_assignment_ids"], "evidence collector assignment ids")
        if not set(producers + collectors).issubset(assignment_ids):
            raise SelectionAuthorityError("independence lineage references an unknown assignment")
        source_digests = _unique_strings(value["source_binding_digests"], "source binding digests")
        if not source_digests:
            raise SelectionAuthorityError("independence constraints require sealed source bindings")
        for source_digest in source_digests:
            _hex(source_digest, "source binding digest")


def _validate_required_constraints(constraints: list[dict[str, Any]], assignments: list[dict[str, Any]]) -> None:
    required = {item["assignment_id"] for item in assignments
                if item["requirements"]["operation"] == "verify"
                and item["requirements"]["risk_class"] == "high"
                and item["requirements"]["independence_required"]}
    counts = {assignment_id: 0 for assignment_id in required}
    for constraint in constraints:
        assignment_id = constraint["assignment_id"]
        if assignment_id not in required:
            raise SelectionAuthorityError("independence constraint targets a verifier that does not require it")
        counts[assignment_id] += 1
    if any(count != 1 for count in counts.values()):
        raise SelectionAuthorityError("each independent high-risk verifier requires exactly one constraint")


def validate_selection_authority(envelope: dict[str, Any]) -> None:
    assignments = envelope["logical_assignments"]
    inputs = envelope["selection_inputs"]
    authority_fields = {
        "schema_version", "issuer", "work_id", "attempt_id", "generation", "sealed_at",
        "charter_digest", "manifest_digest",
        "requirements_digests", "policy_digest", "catalog_digest", "availability_digest",
        "independence_constraints", "prior_authority_digest", "successor_authority_digest",
        "authority_digest",
    }
    authority = _closed(envelope.get("selection_authority"), authority_fields, "selection authority")
    if authority["schema_version"] != 1 or authority["issuer"] != "flow":
        raise SelectionAuthorityError("selection authority issuer or schema is invalid")
    if authority["work_id"] != envelope["work_id"] or authority["attempt_id"] != envelope["attempt_id"]:
        raise SelectionAuthorityError("selection authority run binding mismatch")
    if (authority["charter_digest"] != envelope["charter_digest"]
            or authority["manifest_digest"] != envelope["manifest_digest"]):
        raise SelectionAuthorityError("selection authority charter binding mismatch")
    if type(authority["generation"]) is not int or authority["generation"] < 1:
        raise SelectionAuthorityError("selection authority generation is invalid")
    _timestamp(authority["sealed_at"], "selection authority sealed_at")
    if authority["prior_authority_digest"] is not None:
        _hex(authority["prior_authority_digest"], "prior authority digest")
    assignment_ids = {item["assignment_id"] for item in assignments}
    for assignment in assignments:
        validate_requirements(assignment["requirements"])
    expected_requirements = {item["assignment_id"]: digest(item["requirements"]) for item in assignments}
    if authority["requirements_digests"] != expected_requirements:
        raise SelectionAuthorityError("selection authority requirements digest mismatch")
    validate_effective_policy(inputs["policy"])
    validate_catalog(inputs["catalog"])
    validate_availability_snapshot(inputs["availability"], sealed_at=authority["sealed_at"])
    catalog_ids = {item["candidate_id"] for item in inputs["catalog"]}
    availability_ids = {item["candidate_id"] for item in inputs["availability"]}
    if catalog_ids != availability_ids:
        raise SelectionAuthorityError("availability must contain exactly one record per candidate")
    _validate_constraints(authority["independence_constraints"], assignment_ids)
    _validate_required_constraints(authority["independence_constraints"], assignments)
    if authority["policy_digest"] != inputs["policy"]["policy_digest"]:
        raise SelectionAuthorityError("selection authority policy digest mismatch")
    if authority["catalog_digest"] != digest(inputs["catalog"]) or authority["availability_digest"] != digest(inputs["availability"]):
        raise SelectionAuthorityError("selection authority input digest mismatch")
    expected_successor = successor_authority_digest(
        work_id=envelope["work_id"], attempt_id=envelope["attempt_id"],
        charter_digest=envelope["charter_digest"], manifest_digest=envelope["manifest_digest"],
        generation=authority["generation"], sealed_at=authority["sealed_at"],
        logical_assignments=assignments, catalog=inputs["catalog"], availability=inputs["availability"],
        independence_constraints=authority["independence_constraints"],
        prior_authority_digest=authority["prior_authority_digest"],
    )
    if authority["successor_authority_digest"] != expected_successor:
        raise SelectionAuthorityError("successor authority digest mismatch")
    expected_authority = digest({key: item for key, item in authority.items() if key != "authority_digest"})
    if authority["authority_digest"] != expected_authority:
        raise SelectionAuthorityError("selection authority digest mismatch")
    waiver = inputs["policy"]["independence_waiver"]
    if waiver is not None:
        _resolve_waiver_approval(envelope, waiver)
        prior_policy = deepcopy(inputs["policy"])
        prior_policy["independence_waiver"] = None
        prior_policy["provenance"].pop("independence_waiver", None)
        prior_policy["policy_digest"] = digest({
            key: item for key, item in prior_policy.items() if key != "policy_digest"
        })
        if (waiver["work_id"] != envelope["work_id"] or waiver["attempt_id"] != envelope["attempt_id"]
                or waiver["successor_authority_digest"] != expected_successor
                or waiver["prior_policy_digest"] != prior_policy["policy_digest"]):
            raise SelectionAuthorityError("independence waiver successor authority binding mismatch")
        matching = [item for item in authority["independence_constraints"]
                    if item["assignment_id"] == waiver["assignment_id"]]
        if (len(matching) != 1 or matching[0]["risk_class"] != waiver["risk_class"]
                or matching[0]["excluded_provider_families"] != waiver["excluded_provider_families"]):
            raise SelectionAuthorityError("independence waiver family scope mismatch")


def effective_family_exclusions(envelope: dict[str, Any], assignment_id: str) -> list[str]:
    """Return sealed exclusions minus only an exactly scoped approved exception."""
    constraints = [item for item in envelope["selection_authority"]["independence_constraints"]
                   if item["assignment_id"] == assignment_id]
    if not constraints:
        return []
    excluded = list(constraints[0]["excluded_provider_families"])
    waiver = envelope["selection_inputs"]["policy"]["independence_waiver"]
    if waiver is None or waiver["assignment_id"] != assignment_id:
        return excluded
    waived = set(waiver["waived_provider_families"])
    return [family for family in excluded if family not in waived]
