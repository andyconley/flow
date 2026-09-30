"""Normalized, credential-free provider readiness for deterministic selection."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable


AVAILABILITY_STATES = frozenset({"ready", "unavailable", "unknown", "stale"})
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"


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
    if not isinstance(evidence_code, str) or not evidence_code:
        raise AvailabilityError("availability evidence_code must be nonblank")
    if not isinstance(probe_version, str) or not probe_version:
        raise AvailabilityError("availability probe_version must be nonblank")
    observed = _timestamp(observed_at, "observed_at")
    expires = _timestamp(expires_at, "expires_at")
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
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
    *, opener: Callable[..., Any] = urllib.request.urlopen, timeout: float = 2.0
) -> list[str]:
    """Discover installed model names from loopback only.

    Discovery establishes presence, never capability. Redirects are refused by
    requiring the response URL to remain the exact loopback endpoint.
    """
    request = urllib.request.Request(OLLAMA_TAGS_URL, method="GET")
    try:
        response = opener(request, timeout=timeout)
        response_url = response.geturl() if hasattr(response, "geturl") else OLLAMA_TAGS_URL
        if response_url != OLLAMA_TAGS_URL:
            raise AvailabilityError("ollama discovery redirect refused")
        body = response.read(1_048_577)
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
