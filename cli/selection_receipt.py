"""Offline-recomputable protocol-v9 provider-selection receipts."""

from __future__ import annotations

from typing import Any

try:
    from delivery_selection import compute_binding
    from execution_contracts import ContractError, validate_action, validate_envelope
    from provider_selection import canonical_bytes, digest
    from verifier_contracts import evaluate_candidate, validate_evaluation
except ModuleNotFoundError:  # Package import.
    from .delivery_selection import compute_binding
    from .execution_contracts import ContractError, validate_action, validate_envelope
    from .provider_selection import canonical_bytes, digest
    from .verifier_contracts import evaluate_candidate, validate_evaluation


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
    semantic = receipt.get("semantic_verification", [])
    if not isinstance(actions, list) or not isinstance(selections, list):
        raise V9ReceiptError("v9_selection_rows_missing")
    if any(not isinstance(action, dict) for action in actions) \
            or any(not isinstance(row, dict) for row in selections):
        raise V9ReceiptError("v9_selection_rows_invalid")
    if not isinstance(semantic, list) or any(not isinstance(item, dict) for item in semantic):
        raise V9ReceiptError("v9_semantic_verification_invalid")
    termination = receipt.get("termination")
    if termination is not None:
        fields = {"schema_version", "status", "actor", "explanation", "cause", "owner_generation"}
        if (not isinstance(termination, dict) or set(termination) != fields or termination["schema_version"] != 1
                or termination["status"] not in {"cancelled", "abandoned"}
                or not isinstance(termination["actor"], str) or not termination["actor"].strip()
                or not isinstance(termination["explanation"], str) or not termination["explanation"].strip()
                or not isinstance(termination["cause"], str) or not termination["cause"]
                or type(termination["owner_generation"]) is not int or termination["owner_generation"] < 1):
            raise V9ReceiptError("v9_termination_invalid")
    rows = {row.get("selection_id"): row for row in selections if isinstance(row, dict)}
    if len(rows) != len(selections) or None in rows:
        raise V9ReceiptError("v9_selection_identity_invalid")
    action_selection_ids: set[str] = set()
    action_ids: set[str] = set()
    compared = 0
    completed_bindings: dict[str, list[dict[str, Any]]] = {}

    def runtime_families_for(assignment_id: str) -> list[str] | None:
        constraints = [item for item in envelope["selection_authority"]["independence_constraints"]
                       if item["assignment_id"] == assignment_id]
        if not constraints:
            return None
        if len(constraints) != 1:
            raise V9ReceiptError("v9_independence_constraint_invalid")
        families: list[str] = []
        source_ids = (constraints[0]["producer_assignment_ids"]
                      + constraints[0]["evidence_collector_assignment_ids"])
        for source_id in source_ids:
            bindings = completed_bindings.get(source_id, [])
            if len(bindings) != 1:
                raise V9ReceiptError("v9_independence_lineage_incomplete")
            family = bindings[0].get("provider_family")
            if not isinstance(family, str) or not family:
                raise V9ReceiptError("v9_independence_family_invalid")
            if family not in families:
                families.append(family)
        return families

    for action in actions:
        try:
            validate_action(envelope, action)
        except (TypeError, ContractError) as exc:
            raise V9ReceiptError("v9_action_invalid", str(exc)) from exc
        if action["selection_id"] in action_selection_ids:
            raise V9ReceiptError("v9_duplicate_selection_action")
        if action["action_id"] in action_ids:
            raise V9ReceiptError("v9_duplicate_provider_action")
        action_selection_ids.add(action["selection_id"])
        action_ids.add(action["action_id"])
        row = rows.get(action["selection_id"])
        if row is None:
            raise V9ReceiptError("v9_selection_row_missing", action["selection_id"])
        if row.get("logical_action_id") != action["logical_action_id"]:
            raise V9ReceiptError("v9_logical_action_mismatch")
        prior = row.get("prior_no_send_failures", [])
        if not isinstance(prior, list) or any(not isinstance(item, str) for item in prior) \
                or len(set(prior)) != len(prior):
            raise V9ReceiptError("v9_prior_no_send_failures_invalid")
        runtime_families = runtime_families_for(action["assignment_id"])
        expected = compute_binding(
            envelope, action["assignment_id"], prior_no_send_failures=prior,
            runtime_excluded_families=runtime_families,
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
        state = row.get("state")
        if state == "consumed" and row.get("provider_action_id") != action["action_id"]:
            raise V9ReceiptError("v9_consumed_action_mismatch")
        if state in {"superseded", "pre_send_refused"} and \
                (row.get("provider_action_id") is not None or not row.get("reason")):
            raise V9ReceiptError("v9_unconsumed_selection_closure_invalid")
        if state not in {"consumed", "superseded", "pre_send_refused"}:
            raise V9ReceiptError("v9_selection_state_unsealed")
        if state == "consumed" and actual.get("selected_binding") is not None:
            completed_bindings.setdefault(action["assignment_id"], []).append(actual["selected_binding"])
        compared += 4
    orphan_ids = set(rows) - action_selection_ids
    for selection_id in orphan_ids:
        row = rows[selection_id]
        successors = [item for item in selections if item.get("predecessor_selection_id") == selection_id]
        if (row.get("state") != "superseded" or row.get("provider_action_id") is not None
                or not row.get("reason") or len(successors) != 1
                or successors[0].get("logical_action_id") != row.get("logical_action_id")
                or row.get("candidate_id") not in successors[0].get("prior_no_send_failures", [])):
            raise V9ReceiptError("v9_orphan_selection_row", selection_id)
        successor_action = next((action for action in actions
                                 if action.get("selection_id") == successors[0].get("selection_id")), None)
        if successor_action is None:
            raise V9ReceiptError("v9_orphan_selection_row", selection_id)
        expected = compute_binding(
            envelope, successor_action["assignment_id"],
            prior_no_send_failures=row.get("prior_no_send_failures", []),
            runtime_excluded_families=runtime_families_for(successor_action["assignment_id"]),
        )
        if row.get("decision_digest") != expected.get("decision_digest") \
                or row.get("candidate_id") != expected.get("selected_candidate_id"):
            raise V9ReceiptError("v9_orphan_selection_decision_mismatch", selection_id)
        compared += 4
    consumed = [row for row in selections if row.get("state") == "consumed"]
    if len({row.get("provider_action_id") for row in consumed}) != len(consumed):
        raise V9ReceiptError("v9_duplicate_consumed_action")
    for row in selections:
        predecessor = row.get("predecessor_selection_id")
        if predecessor is not None:
            prior = rows.get(predecessor)
            expected_history = ([*prior.get("prior_no_send_failures", []), prior.get("candidate_id")]
                                if prior is not None else None)
            if prior is None or prior.get("state") != "superseded" \
                    or not prior.get("reason") or row.get("prior_no_send_failures") != expected_history:
                raise V9ReceiptError("v9_fallback_lineage_invalid")
            compared += 1
    assignments = {item["assignment_id"]: item for item in envelope["logical_assignments"]}
    verifier_actions = [action for action in actions
                        if assignments[action["assignment_id"]]["requirements"].get("operation") == "verify"]
    semantic_by_action = {item.get("action_id"): item for item in semantic}
    if len(semantic_by_action) != len(semantic) or set(semantic_by_action) != {
            action["action_id"] for action in verifier_actions}:
        raise V9ReceiptError("v9_semantic_verification_missing")
    for action in verifier_actions:
        item = semantic_by_action[action["action_id"]]
        required = {"action_id", "input", "input_digest", "diff_digest", "test_digest",
                    "result", "evaluation"}
        if set(item) != required or item["action_id"] != action["action_id"]:
            raise V9ReceiptError("v9_semantic_verification_invalid")
        if item["input"] != {"provider_task": action["task"], "assignment_id": action["assignment_id"]} \
                or item["input_digest"] != digest(item["input"]):
            raise V9ReceiptError("v9_verifier_input_mismatch")
        output = item["result"].get("output") if isinstance(item["result"], dict) else None
        if not isinstance(output, str):
            raise V9ReceiptError("v9_verifier_result_invalid")
        try:
            evaluation = validate_evaluation(item["evaluation"])
            expected_evaluation = evaluate_candidate(
                action_id=action["action_id"], verifier_input_digest=item["input_digest"],
                raw_output=output, diff_digest=item["diff_digest"],
                test_evidence_digest=item["test_digest"],
            )
        except Exception as exc:
            raise V9ReceiptError("v9_verifier_evaluation_invalid", str(exc)) from exc
        if evaluation != expected_evaluation:
            raise V9ReceiptError("v9_verifier_evaluation_mismatch")
        compared += 7
    expected_digest = digest({key: value for key, value in receipt.items() if key != "receipt_digest"})
    if receipt.get("receipt_digest") != expected_digest:
        raise V9ReceiptError("v9_receipt_digest_mismatch")
    return {"schema_version": 1, "execution_protocol_version": 9, "status": "valid_pass",
            "compared": compared, "receipt_digest": expected_digest}


def seal_selection_receipt(envelope: dict[str, Any], actions: list[dict[str, Any]],
                           selections: list[dict[str, Any]], *,
                           semantic_verification: list[dict[str, Any]] | None = None,
                           termination: dict[str, Any] | None = None) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "execution_protocol_version": 9,
        "envelope": envelope,
        "actions": actions,
        "selections": selections,
        "semantic_verification": semantic_verification or [],
    }
    if termination is not None:
        receipt["termination"] = termination
    receipt["receipt_digest"] = digest(receipt)
    verify_selection_receipt(receipt)
    return receipt


def receipt_from_snapshot(snapshot: dict[str, Any], *, termination: dict[str, Any] | None = None) -> dict[str, Any]:
    """Render the complete v9 receipt from one ledger snapshot.

    The caller must obtain the snapshot under its terminal-seal transaction.
    This function is deliberately pure so the bytes it returns can be checked
    before they are published or attached to the attempt.
    """
    if not isinstance(snapshot, dict) or snapshot.get("execution_protocol_version") != 9:
        raise V9ReceiptError("v9_snapshot_protocol_invalid")
    envelope = snapshot.get("envelope")
    actions = [item.get("request") for item in snapshot.get("actions", [])
               if isinstance(item, dict)]
    if len(actions) != len(snapshot.get("actions", [])) or any(not isinstance(item, dict) for item in actions):
        raise V9ReceiptError("v9_snapshot_actions_invalid")
    rows = []
    for item in snapshot.get("provider_selections", []):
        if not isinstance(item, dict) or not isinstance(item.get("decision"), dict):
            raise V9ReceiptError("v9_snapshot_selection_invalid")
        rows.append({
            "selection_id": item.get("selection_id"),
            "logical_action_id": item.get("logical_action_id"),
            "decision_digest": item.get("decision_digest"),
            "candidate_id": item.get("candidate_id"),
            "state": item.get("state"),
            "reason": item.get("reason"),
            "predecessor_selection_id": item.get("predecessor_selection_id"),
            "provider_action_id": item.get("provider_action_id"),
            "prior_no_send_failures": item["decision"].get("prior_no_send_failures"),
        })
    action_results = {item["action_id"]: (item.get("result") or {}).get("result")
                      for item in snapshot.get("actions", [])}
    inputs = {item["action_id"]: item for item in snapshot.get("verifier_inputs", [])}
    evaluations = {item["action_id"]: item for item in snapshot.get("verifier_evaluations", [])}
    semantic = []
    for action_id in sorted(set(inputs) | set(evaluations)):
        binding, evaluation = inputs.get(action_id), evaluations.get(action_id)
        if binding is None or evaluation is None:
            raise V9ReceiptError("v9_snapshot_semantic_verification_incomplete")
        semantic.append({
            "action_id": action_id, "input": binding["input"], "input_digest": binding["input_digest"],
            "diff_digest": binding["diff_digest"], "test_digest": binding["test_digest"],
            "result": action_results.get(action_id), "evaluation": evaluation["evaluation"],
        })
    return seal_selection_receipt(envelope, actions, rows, semantic_verification=semantic,
                                  termination=termination)


def verify_selection_receipt_snapshot(receipt: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Verify a v9 receipt and its exact ledger-derived closure."""
    result = verify_selection_receipt(receipt)
    expected = receipt_from_snapshot(snapshot)
    for field in ("envelope", "actions", "selections", "semantic_verification"):
        if canonical_bytes(receipt.get(field)) != canonical_bytes(expected.get(field)):
            raise V9ReceiptError(f"v9_ledger_{field}_mismatch")
    return result


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
