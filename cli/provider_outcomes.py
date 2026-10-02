"""Closed, receipt-safe provider outcomes observed by Flow adapters.

Only an adapter's bounded terminal response may create an
``ObservedNotExecuted`` outcome.  It carries no provider prose and is distinct
from every timeout, malformed response, or transport loss, which remains
uncertain under the send fence.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Final


OBSERVED_NOT_EXECUTED_CATEGORIES: Final[frozenset[str]] = frozenset({
    "model_capacity",
})


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ObservedNotExecuted(RuntimeError):
    """A terminal provider refusal whose fixed category proves no turn ran."""

    def __init__(self, *, provider: str, category: str, observation_sha256: str) -> None:
        if provider not in {"codex", "claude"}:
            raise ValueError("observed provider is invalid")
        if category not in OBSERVED_NOT_EXECUTED_CATEGORIES:
            raise ValueError("observed refusal category is invalid")
        if not isinstance(observation_sha256, str) or not _SHA256.fullmatch(observation_sha256):
            raise ValueError("observed refusal digest is invalid")
        self.provider = provider
        self.category = category
        self.observation_sha256 = observation_sha256
        super().__init__(f"{provider} provider refusal: {category}")

    def receipt_result(self) -> dict[str, object]:
        """The complete receipt-safe observation; raw provider text is excluded."""
        controlled: dict[str, object] = {
            "schema_version": 1,
            "kind": "observed_not_executed",
            "disposition": "observed_not_executed",
            "adapter_schema_version": 1,
            "provider": self.provider,
            "category": self.category,
            "terminal": True,
            "execution_events": 0,
        }
        controlled["observation_sha256"] = hashlib.sha256(
            json.dumps(controlled, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        controlled["diagnostic_sha256"] = self.observation_sha256
        return controlled
