"""Normalized, credential-free provider readiness for deterministic selection."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


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
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AvailabilityError("ollama discovery redirect refused")


class AvailabilityError(ValueError):
    """Raised when readiness evidence is not safe to use."""


def normalize_availability(record: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Return the bounded readiness fields used by the pure selector.

    Raw probe bodies, credentials, and exception text deliberately never cross
    this boundary. Expired observations normalize to ``stale``.
    """
    candidate_id = record.get("candidate_id")
    state = record.get("state")
    observed_at = record.get("observed_at")
    expires_at = record.get("expires_at")
    evidence_code = record.get("evidence_code")
    probe_version = record.get("probe_version", "availability-v1")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise AvailabilityError("availability candidate_id must be nonblank")
    if state not in AVAILABILITY_STATES:
        raise AvailabilityError("availability state is unsupported")
    if evidence_code not in AVAILABILITY_EVIDENCE_CODES:
        raise AvailabilityError("availability evidence_code is unsupported")
    if probe_version != "availability-v1":
        raise AvailabilityError("availability probe_version is unsupported")
    if evidence_code not in AVAILABILITY_EVIDENCE_BY_STATE[state]:
        raise AvailabilityError("availability evidence contradicts state")
    observed = _timestamp(observed_at, "observed_at")
    expires = _timestamp(expires_at, "expires_at")
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    clock = clock.astimezone(timezone.utc)
    observed = observed.astimezone(timezone.utc)
    expires = expires.astimezone(timezone.utc)
    if expires <= observed or expires - observed > MAX_AVAILABILITY_TTL:
        raise AvailabilityError("availability freshness window is invalid")
    if observed > clock + MAX_FUTURE_SKEW:
        raise AvailabilityError("availability observation is from the future")
    if expires <= clock:
        state = "stale"
        evidence_code = "observation_expired"
    return {
        "schema_version": 1,
        "candidate_id": candidate_id,
        "state": state,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "evidence_code": evidence_code,
        "probe_version": probe_version,
    }


def discover_ollama_models(
    *, opener: Callable[..., Any] | None = None, timeout: float = 2.0
) -> list[str]:
    """Discover installed model names from loopback only.

    Discovery establishes presence, never capability. Redirects are refused by
    requiring the response URL to remain the exact loopback endpoint.
    """
    request = urllib.request.Request(OLLAMA_TAGS_URL, method="GET")
    opener = opener or urllib.request.build_opener(_NoRedirect()).open
    try:
        response = opener(request, timeout=timeout)
        response_url = response.geturl() if hasattr(response, "geturl") else OLLAMA_TAGS_URL
        if response_url != OLLAMA_TAGS_URL:
            raise AvailabilityError("ollama discovery redirect refused")
        body = response.read(1_048_577)
    except AvailabilityError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise AvailabilityError("ollama discovery unavailable") from exc
    if len(body) > 1_048_576:
        raise AvailabilityError("ollama discovery response exceeds limit")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AvailabilityError("ollama discovery returned invalid JSON") from exc
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise AvailabilityError("ollama discovery response lacks models")
    names = {
        item.get("name") for item in models
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]
    }
    return sorted(names)


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AvailabilityError(f"availability {field} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AvailabilityError(f"availability {field} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise AvailabilityError(f"availability {field} must include a timezone")
    return parsed
