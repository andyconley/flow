"""Pure model-policy resolution for delegated agents and parent sessions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIMES = ("claude", "codex")
PROFILE_IDS = ("mechanical", "working", "judgment", "demanding")
EFFORT_FIELDS = {"claude": "effort", "codex": "model_reasoning_effort"}
EFFORT_VALUES = {
    "claude": {"low", "medium", "high"},
    "codex": {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"},
}


class ModelPolicyError(ValueError):
    """Raised when model policy configuration is structurally invalid."""


def runtime_policy_for_agent(manifest: dict, target: str, agent: dict) -> dict:
    """Resolve one delegated agent, preserving established precedence."""
    tiers = manifest.get("model_tiers", {})
    tier = agent.get("model_tier")
    policy = dict(tiers.get(tier, {}).get(target, {}))
    runtime_override = agent.get(target)
    if isinstance(runtime_override, dict):
        policy.update(runtime_override)
    for key in ("model", "effort", "model_reasoning_effort"):
        if key in agent:
            policy[key] = agent[key]
    return policy


def merge_session_model_profiles(
    framework_manifest: dict,
    user_manifest: dict | None,
    *,
    framework_source: str,
    user_source: str,
) -> dict[str, dict]:
    """Merge profiles atomically per profile/runtime and attach provenance."""
    framework = framework_manifest.get("session_model_profiles")
    if framework is None:
        return {}
    if not isinstance(framework, dict):
        raise ModelPolicyError("session_model_profiles must be a table")
    merged = deepcopy(framework)
    provenance: dict[tuple[str, str], str] = {}
    for profile, definition in merged.items():
        if isinstance(definition, dict):
            for runtime in RUNTIMES:
                if runtime in definition:
                    provenance[(profile, runtime)] = framework_source

    user_profiles = (user_manifest or {}).get("session_model_profiles", {})
    if not isinstance(user_profiles, dict):
        raise ModelPolicyError("user session_model_profiles must be a table")
    for profile, override in user_profiles.items():
        if profile not in PROFILE_IDS:
            raise ModelPolicyError(f"unknown session model profile: {profile}")
        if not isinstance(override, dict):
            raise ModelPolicyError(f"session model profile {profile} must be a table")
        target = merged.setdefault(profile, {})
        if not isinstance(target, dict):
            raise ModelPolicyError(f"session model profile {profile} must be a table")
        if "description" in override:
            raise ModelPolicyError(
                f"session model profile {profile} description is framework-owned; "
                "override runtime mappings instead"
            )
        for runtime in RUNTIMES:
            if runtime in override:
                target[runtime] = deepcopy(override[runtime])
                provenance[(profile, runtime)] = user_source

    validate_session_model_profiles(merged, framework_manifest.get("model_tiers", {}))
    for profile, definition in merged.items():
        for runtime in RUNTIMES:
            entry = definition.get(runtime)
            if isinstance(entry, dict):
                entry["_provenance"] = provenance.get((profile, runtime), framework_source)
    return merged


def validate_session_model_profiles(profiles: dict, model_tiers: dict) -> None:
    for profile, definition in profiles.items():
        if profile not in PROFILE_IDS:
            raise ModelPolicyError(f"unknown session model profile: {profile}")
        if not isinstance(definition, dict):
            raise ModelPolicyError(f"session model profile {profile} must be a table")
        description = definition.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ModelPolicyError(f"session model profile {profile} needs a description")
        for runtime in RUNTIMES:
            if runtime in definition:
                entry = definition[runtime]
                if not isinstance(entry, dict):
                    raise ModelPolicyError(f"{profile}.{runtime} must be a table")
                _validate_profile_entry(profile, runtime, entry, model_tiers)


def _validate_profile_entry(profile: str, runtime: str, entry: dict, model_tiers: dict) -> None:
    label = f"{profile}.{runtime}"
    disabled = entry.get("disabled") is True
    if "disabled" in entry and not isinstance(entry["disabled"], bool):
        raise ModelPolicyError(f"{label}.disabled must be a boolean")
    if disabled:
        forbidden = {"tier", "model", "effort", "model_reasoning_effort"} & set(entry)
        if forbidden:
            raise ModelPolicyError(f"{label} disabled mapping cannot also set {', '.join(sorted(forbidden))}")
        return
    tier = entry.get("tier")
    model = entry.get("model")
    if tier is not None and (not isinstance(tier, str) or not tier.strip()):
        raise ModelPolicyError(f"{label}.tier must be a nonblank string")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ModelPolicyError(f"{label}.model must be a nonblank string")
    if bool(tier) == bool(model):
        raise ModelPolicyError(f"{label} must set exactly one of tier or model")
    if tier:
        if tier not in model_tiers or runtime not in model_tiers[tier]:
            raise ModelPolicyError(f"{label} references unknown {runtime} tier {tier!r}")
        if "effort" in entry or "model_reasoning_effort" in entry:
            raise ModelPolicyError(f"{label} tier mapping cannot override native effort")
    else:
        effort_field = EFFORT_FIELDS[runtime]
        other_field = EFFORT_FIELDS["codex" if runtime == "claude" else "claude"]
        if other_field in entry:
            raise ModelPolicyError(f"{label} uses cross-runtime effort field {other_field}")
        if entry.get(effort_field) not in EFFORT_VALUES[runtime]:
            raise ModelPolicyError(f"{label}.{effort_field} is not a supported {runtime} effort")
    for field in ("rationale", "source", "verified_at"):
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ModelPolicyError(f"{label} needs {field}")


def resolve_session_profile(manifest: dict, runtime: str, profile: str) -> dict[str, Any]:
    """Resolve a semantic parent-session profile for one active runtime."""
    base = {
        "schema_version": 1,
        "runtime": runtime,
        "profile": profile,
        "status": "unresolved",
        "model": None,
        "effort": None,
        "provenance": None,
        "reason_codes": [],
    }
    if runtime not in RUNTIMES:
        return {**base, "status": "invalid", "reason_codes": ["unsupported_runtime"]}
    if profile not in PROFILE_IDS:
        return {**base, "status": "invalid", "reason_codes": ["unknown_profile"]}
    profiles = manifest.get("session_model_profiles")
    if not isinstance(profiles, dict):
        return {**base, "reason_codes": ["profiles_absent"]}
    definition = profiles.get(profile)
    if not isinstance(definition, dict):
        return {**base, "reason_codes": ["profile_unmapped"]}
    entry = definition.get(runtime)
    if not isinstance(entry, dict):
        return {**base, "reason_codes": ["runtime_unmapped"]}
    if entry.get("disabled") is True:
        return {
            **base,
            "status": "disabled",
            "provenance": entry.get("_provenance"),
            "reason_codes": ["mapping_disabled"],
        }
    try:
        _validate_profile_entry(profile, runtime, entry, manifest.get("model_tiers", {}))
    except ModelPolicyError as exc:
        return {**base, "status": "invalid", "reason_codes": ["invalid_mapping"], "detail": str(exc)}
    if entry.get("tier"):
        tier = entry["tier"]
        policy = manifest["model_tiers"][tier][runtime]
        provenance = {"profile": entry.get("_provenance"), "mapping": f"model_tiers.{tier}.{runtime}"}
    else:
        policy = entry
        provenance = {"profile": entry.get("_provenance"), "mapping": "literal"}
    effort_field = EFFORT_FIELDS[runtime]
    model = policy.get("model")
    effort = policy.get(effort_field)
    if not model or effort not in EFFORT_VALUES[runtime]:
        return {**base, "status": "invalid", "reason_codes": ["invalid_resolved_policy"]}
    return {
        **base,
        "status": "resolved",
        "model": model,
        "effort": effort,
        "provenance": provenance,
        "reason_codes": ["mapping_resolved"],
        "intended_use": definition.get("description"),
        "rationale": entry.get("rationale"),
        "source": entry.get("source"),
        "verified_at": entry.get("verified_at"),
    }
