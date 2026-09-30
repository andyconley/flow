"""Offline-recomputable protocol-v9 provider-selection receipts."""

from __future__ import annotations

from typing import Any

try:
    from delivery_selection import compute_binding
    from execution_contracts import ContractError, validate_action, validate_envelope
    from provider_selection import digest
except ModuleNotFoundError:  # Package import.
    from .delivery_selection import compute_binding
    from .execution_contracts import ContractError, validate_action, validate_envelope
    from .provider_selection import digest


DECISION_FIELDS = (
    "requirements_digest", "policy_digest", "catalog_digest", "availability_digest",
    "prior_no_send_failures", "excluded_families", "exclusions", "ordered_candidates",
    "selected_candidate_id", "selected_binding", "decision_digest",
)


class V9ReceiptError(ContractError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(code + (f": {detail}" if detail else ""))


def verify_selection_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1 \
            or receipt.get("execution_protocol_version") != 9:
        raise V9ReceiptError("v9_receipt_schema_invalid")
    envelope = receipt.get("envelope")
    try:
        validate_envelope(envelope)
    except (TypeError, ContractError) as exc:
        raise V9ReceiptError("v9_envelope_invalid", str(exc)) from exc
    actions = receipt.get("actions")
    selections = receipt.get("selections")
    if not isinstance(actions, list) or not isinstance(selections, list):
        raise V9ReceiptError("v9_selection_rows_missing")
    rows = {row.get("selection_id"): row for row in selections if isinstance(row, dict)}
    if len(rows) != len(selections) or None in rows:
        raise V9ReceiptError("v9_selection_identity_invalid")
    compared = 0
    for action in actions:
        try:
            validate_action(envelope, action)
        except (TypeError, ContractError) as exc:
            raise V9ReceiptError("v9_action_invalid", str(exc)) from exc
        row = rows.get(action["selection_id"])
        if row is None:
            raise V9ReceiptError("v9_selection_row_missing", action["selection_id"])
        if row.get("logical_action_id") != action["logical_action_id"]:
            raise V9ReceiptError("v9_logical_action_mismatch")
        prior = row.get("prior_no_send_failures", [])
        expected = compute_binding(
            envelope, action["assignment_id"], prior_no_send_failures=prior
        )
        actual = action["selection_decision"]
        for field in DECISION_FIELDS:
            if actual.get(field) != expected.get(field):
                raise V9ReceiptError(f"v9_{field}_mismatch")
            compared += 1
        if row.get("decision_digest") != actual["decision_digest"]:
            raise V9ReceiptError("v9_selection_row_digest_mismatch")
        if row.get("candidate_id") != actual["selected_candidate_id"]:
            raise V9ReceiptError("v9_selection_row_candidate_mismatch")
        if row.get("state") == "consumed" and row.get("provider_action_id") != action["action_id"]:
            raise V9ReceiptError("v9_consumed_action_mismatch")
        if row.get("state") not in {"consumed", "superseded", "pre_send_refused"}:
            raise V9ReceiptError("v9_selection_state_unsealed")
        compared += 4
    consumed = [row for row in selections if row.get("state") == "consumed"]
    if len({row.get("provider_action_id") for row in consumed}) != len(consumed):
        raise V9ReceiptError("v9_duplicate_consumed_action")
    for row in selections:
        predecessor = row.get("predecessor_selection_id")
        if predecessor is not None:
            prior = rows.get(predecessor)
            if prior is None or prior.get("state") != "superseded" \
                    or not prior.get("reason") or prior.get("candidate_id") not in row.get("prior_no_send_failures", []):
                raise V9ReceiptError("v9_fallback_lineage_invalid")
            compared += 1
    expected_digest = digest({key: value for key, value in receipt.items() if key != "receipt_digest"})
    if receipt.get("receipt_digest") != expected_digest:
        raise V9ReceiptError("v9_receipt_digest_mismatch")
    return {"schema_version": 1, "execution_protocol_version": 9, "status": "valid_pass",
            "compared": compared, "receipt_digest": expected_digest}


def seal_selection_receipt(envelope: dict[str, Any], actions: list[dict[str, Any]],
                           selections: list[dict[str, Any]]) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "execution_protocol_version": 9,
        "envelope": envelope,
        "actions": actions,
        "selections": selections,
    }
    receipt["receipt_digest"] = digest(receipt)
    verify_selection_receipt(receipt)
    return receipt


def project_selection_trace(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    """Structured selection/fallback chain; no narrative parsing."""
    rows = {row["selection_id"]: row for row in receipt.get("selections", [])}
    return [{
        "selection_id": row["selection_id"],
        "predecessor_selection_id": row.get("predecessor_selection_id"),
        "candidate_id": row.get("candidate_id"),
        "state": row.get("state"),
        "reason": row.get("reason", ""),
        "successors": sorted(item["selection_id"] for item in rows.values()
                             if item.get("predecessor_selection_id") == row["selection_id"]),
    } for row in sorted(rows.values(), key=lambda item: item["selection_id"])]
