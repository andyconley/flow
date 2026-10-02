"""Closed, receipt-safe provider outcomes observed by Flow adapters.

Only an adapter's bounded terminal response may create an
``ObservedNotExecuted`` outcome.  It carries no provider prose and is distinct
from every timeout, malformed response, or transport loss, which remains
uncertain under the send fence.
"""

from __future__ import annotations

from typing import Final


OBSERVED_NOT_EXECUTED_CATEGORIES: Final[frozenset[str]] = frozenset({
    "model_capacity",
})


class ObservedNotExecuted(RuntimeError):
    """A terminal provider refusal whose fixed category proves no turn ran."""

    def __init__(self, *, provider: str, category: str) -> None:
        if provider not in {"codex", "claude"}:
            raise ValueError("observed provider is invalid")
        if category not in OBSERVED_NOT_EXECUTED_CATEGORIES:
            raise ValueError("observed refusal category is invalid")
        self.provider = provider
        self.category = category
        super().__init__(f"{provider} provider refusal: {category}")

    def receipt_result(self) -> dict[str, object]:
        """The complete receipt-safe observation; raw provider text is excluded."""
        return {
            "schema_version": 1,
            "kind": "observed_not_executed",
            "provider": self.provider,
            "category": self.category,
        }
