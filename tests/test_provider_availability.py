from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from provider_availability import (  # noqa: E402
    AvailabilityError,
    OLLAMA_TAGS_URL,
    discover_ollama_models,
    normalize_availability,
)


class Response:
    def __init__(self, payload: dict, url: str = OLLAMA_TAGS_URL) -> None:
        self.payload = json.dumps(payload).encode()
        self.url = url

    def geturl(self) -> str:
        return self.url

    def read(self, _limit: int) -> bytes:
        return self.payload


class ProviderAvailabilityTests(unittest.TestCase):
    def test_expired_observation_normalizes_to_stale_without_raw_probe_data(self) -> None:
        normalized = normalize_availability({
            "candidate_id": "local",
            "state": "ready",
            "observed_at": "2026-09-29T10:00:00Z",
            "expires_at": "2026-09-29T10:01:00Z",
            "evidence_code": "model_present",
            "credential": "must-not-survive",
        }, now=datetime(2026, 9, 29, 11, tzinfo=timezone.utc))
        self.assertEqual(normalized["state"], "stale")
        self.assertEqual(normalized["evidence_code"], "observation_expired")
        self.assertNotIn("credential", normalized)

    def test_model_discovery_is_sorted_presence_only(self) -> None:
        observed = {}

        def opener(_request, **kwargs):
            observed.update(kwargs)
            return Response({"models": [{"name": "zeta"}, {"name": "alpha"}, {"name": "alpha"}]})

        self.assertEqual(discover_ollama_models(opener=opener), ["alpha", "zeta"])
        self.assertIsNone(observed["timeout"])

    def test_invalid_freshness_and_uncontrolled_evidence_are_rejected(self) -> None:
        base = {
            "candidate_id": "local", "state": "ready",
            "observed_at": "2026-09-29T10:00:00Z",
            "expires_at": "2026-09-29T10:06:00Z",
            "evidence_code": "model_present",
        }
        with self.assertRaisesRegex(AvailabilityError, "freshness window"):
            normalize_availability(base, now=datetime(2026, 9, 29, 10, tzinfo=timezone.utc))
        base["expires_at"] = "2026-09-29T10:01:00Z"
        base["evidence_code"] = "raw_exception_text"
        with self.assertRaisesRegex(AvailabilityError, "evidence_code is unsupported"):
            normalize_availability(base, now=datetime(2026, 9, 29, 10, tzinfo=timezone.utc))
        base["evidence_code"] = "model_absent"
        with self.assertRaisesRegex(AvailabilityError, "contradicts state"):
            normalize_availability(base, now=datetime(2026, 9, 29, 10, tzinfo=timezone.utc))

    def test_redirect_is_refused(self) -> None:
        def opener(_request, **_kwargs):
            return Response({"models": []}, "http://example.invalid/api/tags")

        with self.assertRaisesRegex(AvailabilityError, "redirect refused"):
            discover_ollama_models(opener=opener)


if __name__ == "__main__":
    unittest.main()
