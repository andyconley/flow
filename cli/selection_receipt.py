"""Offline-recomputable protocol-v9 provider-selection receipts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

try:
    from delivery_selection import compute_binding
    from execution_contracts import ContractError, validate_action, validate_envelope, validate_local_agent_observations, validate_local_manager_context_refusal
    from provider_selection import canonical_bytes, digest
    from verifier_contracts import evaluate_candidate, validate_evaluation
except ModuleNotFoundError:  # Package import.
    from .delivery_selection import compute_binding
    from .execution_contracts import ContractError, validate_action, validate_envelope, validate_local_agent_observations, validate_local_manager_context_refusal
    from .provider_selection import canonical_bytes, digest
    from .verifier_contracts import evaluate_candidate, validate_evaluation


DECISION_FIELDS = (
    "requirements_digest", "policy_digest", "catalog_digest", "availability_digest",
    "prior_no_send_failures", "prior_retryable_failures", "excluded_families", "exclusions", "ordered_candidates",
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
    evidence_failures = receipt.get("evidence_failures", [])
    provider_refusals = receipt.get("provider_refusals", [])
    if not isinstance(actions, list) or not isinstance(selections, list):
        raise V9ReceiptError("v9_selection_rows_missing")
    if any(not isinstance(action, dict) for action in actions) \
            or any(not isinstance(row, dict) for row in selections):
        raise V9ReceiptError("v9_selection_rows_invalid")
    hosted = receipt.get("hosted_scope_observations", [])
    if not isinstance(hosted, list):
        raise V9ReceiptError("v9_hosted_scope_observations_invalid")
    hosted_by_action = {}
    action_by_identity = {a.get("action_id"): a for a in actions}
    for item in hosted:
        if (not isinstance(item, dict) or set(item) != {"action_id", "evidence", "evidence_digest"}
                or item["action_id"] not in action_by_identity or item["action_id"] in hosted_by_action
                or item["evidence_digest"] != digest(item["evidence"])):
            raise V9ReceiptError("v9_hosted_scope_observation_binding_invalid")
        action = action_by_identity[item["action_id"]]
        evidence = item["evidence"]
        files = evidence.get("source_files") if isinstance(evidence, dict) else None
        if (action.get("selection_decision", {}).get("selected_binding", {}).get("provider") not in {"claude", "codex"}
                or not isinstance(files, dict) or not files
                or evidence.get("scope_enforcement") != "isolated_staging"
                or not evidence.get("changed_files")
                or evidence.get("source_digest") != hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()):
            raise V9ReceiptError("v9_hosted_scope_observations_invalid")
        hosted_by_action[item["action_id"]] = evidence
    observations = receipt.get("local_agent_observations", [])
    if not isinstance(observations, list) or (observations and "local_agent_profile" not in envelope):
        raise V9ReceiptError("v9_local_agent_observations_invalid")
    observed_ids = set()
    action_ids = {item.get("action_id") for item in actions}
    for item in observations:
        if (not isinstance(item, dict) or set(item) != {"action_id", "evidence", "evidence_digest"}
                or item["action_id"] not in action_ids or item["action_id"] in observed_ids
                or item["evidence_digest"] != digest(item["evidence"])):
            raise V9ReceiptError("v9_local_agent_observation_binding_invalid")
        observed_ids.add(item["action_id"])
        try:
            validate_local_agent_observations(item["evidence"], profile=envelope["local_agent_profile"])
        except ContractError as exc:
            raise V9ReceiptError("v9_local_agent_observations_invalid", str(exc)) from exc
    if not isinstance(semantic, list) or any(not isinstance(item, dict) for item in semantic):
        raise V9ReceiptError("v9_semantic_verification_invalid")
    refusal_fields = {"action_id", "selection_id", "schema_version", "kind", "disposition",
                      "adapter_schema_version", "provider", "category", "terminal", "execution_events",
                      "observation_sha256", "diagnostic_sha256"}
    if (not isinstance(provider_refusals, list)
            or any(not isinstance(item, dict) or set(item) != refusal_fields
                   or item.get("schema_version") != 1 or item.get("kind") != "observed_not_executed"
                   or item.get("disposition") != "observed_not_executed"
                   or item.get("adapter_schema_version") != 1
                   or item.get("terminal") is not True or item.get("execution_events") != 0
                   or item.get("provider") not in {"codex", "claude"}
                   or item.get("category") != "model_capacity"
                   or not isinstance(item.get("observation_sha256"), str)
                   or len(item["observation_sha256"]) != 64
                   or any(character not in "0123456789abcdef" for character in item["observation_sha256"])
                   or not isinstance(item.get("diagnostic_sha256"), str)
                   or len(item["diagnostic_sha256"]) != 64
                   or any(character not in "0123456789abcdef" for character in item["diagnostic_sha256"])
                   or hashlib.sha256(canonical_bytes({key: value for key, value in item.items()
                                                      if key not in {"action_id", "selection_id", "observation_sha256",
                                                                     "diagnostic_sha256"}})).hexdigest()
                   != item["observation_sha256"]
                   for item in provider_refusals)):
        raise V9ReceiptError("v9_provider_refusal_invalid")
    refusal_by_action = {item["action_id"]: item for item in provider_refusals}
    if len(refusal_by_action) != len(provider_refusals):
        raise V9ReceiptError("v9_provider_refusal_duplicate")
    if (not isinstance(evidence_failures, list)
            or any(not isinstance(item, dict)
                   or set(item) != {"action_id", "stage", "detail"}
                   or not isinstance(item["action_id"], str)
                   or item["stage"] not in ({"manager_evaluation", "edit_scope", "chartered_test", "verifier_evaluation"}
                       | ({"assignment_evidence"} if "local_agent_profile" in envelope else set()))
                   or not isinstance(item["detail"], str) or not item["detail"]
                   for item in evidence_failures)):
        raise V9ReceiptError("v9_evidence_failures_invalid")
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
    outcome = receipt.get("outcome")
    if (not isinstance(outcome, dict) or set(outcome) != {"status", "reason"}
            or outcome.get("status") not in {"completed", "failed", "cancelled", "abandoned"}
            or not isinstance(outcome.get("reason"), str) or not outcome["reason"]):
        raise V9ReceiptError("v9_outcome_invalid")
    if termination is not None and outcome["status"] != termination["status"]:
        raise V9ReceiptError("v9_outcome_termination_mismatch")
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
        retryable = row.get("prior_retryable_failures", [])
        if (not isinstance(retryable, list) or any(not isinstance(item, str) for item in retryable)
                or len(set(retryable)) != len(retryable) or set(retryable) & set(prior)):
            raise V9ReceiptError("v9_prior_retryable_failures_invalid")
        runtime_families = runtime_families_for(action["assignment_id"])
        expected = compute_binding(
            envelope, action["assignment_id"], prior_no_send_failures=prior,
            prior_retryable_failures=retryable,
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
        observation = next((item["evidence"] for item in observations if item["action_id"] == action["action_id"]), None)
        if (row.get("reason") == "local_manager_context_denied"
                or isinstance(observation, dict) and "context_denial" in observation):
            if state != "pre_send_refused" or row.get("reason") != "local_manager_context_denied":
                raise V9ReceiptError("v9_local_manager_context_refusal_state_invalid")
            try:
                validate_local_manager_context_refusal(envelope, action,
                    {"kind": "local_manager_context_denied", "local_agent_observations": observation})
            except ContractError as exc:
                raise V9ReceiptError("v9_local_manager_context_refusal_invalid", str(exc)) from exc
        if state in {"consumed", "observed_not_executed"} and row.get("provider_action_id") != action["action_id"]:
            raise V9ReceiptError("v9_consumed_action_mismatch")
        if state in {"superseded", "pre_send_refused"} and \
                (row.get("provider_action_id") is not None or not row.get("reason")):
            raise V9ReceiptError("v9_unconsumed_selection_closure_invalid")
        refusal = refusal_by_action.get(action["action_id"])
        if state == "observed_not_executed":
            binding = actual.get("selected_binding") or {}
            if (not row.get("reason") or row.get("reason") != "model_capacity" or refusal is None
                    or refusal["selection_id"] != action["selection_id"]
                    or refusal["provider"] != binding.get("provider")):
                raise V9ReceiptError("v9_observed_refusal_invalid")
        elif refusal is not None:
            raise V9ReceiptError("v9_orphan_provider_refusal")
        if state not in {"consumed", "observed_not_executed", "superseded", "pre_send_refused"}:
            raise V9ReceiptError("v9_selection_state_unsealed")
        if state == "consumed" and actual.get("selected_binding") is not None:
            completed_bindings.setdefault(action["assignment_id"], []).append(actual["selected_binding"])
        compared += 4
    if set(refusal_by_action) - action_ids:
        raise V9ReceiptError("v9_orphan_provider_refusal")
    assignments = {item["assignment_id"]: item for item in envelope["logical_assignments"]}
    actions_by_id = {action["action_id"]: action for action in actions}
    failure_keys: set[tuple[str, str]] = set()
    for failure in evidence_failures:
        action = actions_by_id.get(failure["action_id"])
        operation = (assignments[action["assignment_id"]]["requirements"].get("operation")
                     if action is not None else None)
        expected_operation = ("manage" if failure["stage"] == "manager_evaluation" else
                              "verify" if failure["stage"] == "verifier_evaluation" else "edit")
        if failure["stage"] == "assignment_evidence":
            expected_operation = operation if operation in {"edit", "collect", "verify"} else None
        key = (failure["action_id"], failure["stage"])
        if action is None or expected_operation is None or operation != expected_operation or key in failure_keys:
            raise V9ReceiptError("v9_evidence_failure_binding_invalid")
        failure_keys.add(key)
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
            prior_retryable_failures=row.get("prior_retryable_failures", []),
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
            expected_no_send = (list(prior.get("prior_no_send_failures", [])) if prior is not None else None)
            expected_retryable = (list(prior.get("prior_retryable_failures", [])) if prior is not None else None)
            if prior is not None and prior.get("state") == "superseded":
                expected_no_send.append(prior.get("candidate_id"))
            if prior is not None and prior.get("state") == "observed_not_executed":
                expected_retryable.append(prior.get("candidate_id"))
            if prior is None or prior.get("state") not in {"superseded", "observed_not_executed"} \
                    or not prior.get("reason") or row.get("prior_no_send_failures") != expected_no_send \
                    or row.get("prior_retryable_failures", []) != expected_retryable:
                raise V9ReceiptError("v9_fallback_lineage_invalid")
            compared += 1
    terminal_refusal_exhaustions: list[str] = []
    for row in selections:
        if row.get("state") not in {"observed_not_executed", "pre_send_refused"}:
            continue
        successors = [item for item in selections
                      if item.get("predecessor_selection_id") == row.get("selection_id")]
        if successors:
            continue
        action = next((item for item in actions
                       if item.get("selection_id") == row.get("selection_id")), None)
        if action is None:
            raise V9ReceiptError("v9_terminal_refusal_action_missing")
        no_send = list(row.get("prior_no_send_failures", []))
        retryable = list(row.get("prior_retryable_failures", []))
        if row.get("state") == "pre_send_refused":
            no_send.append(row.get("candidate_id"))
        else:
            retryable.append(row.get("candidate_id"))
        successor = compute_binding(
            envelope, action["assignment_id"],
            prior_no_send_failures=no_send,
            prior_retryable_failures=retryable,
            runtime_excluded_families=runtime_families_for(action["assignment_id"]),
        )
        if successor.get("selected_binding") is None:
            terminal_refusal_exhaustions.append(row["selection_id"])
    selection_state_by_id = {row.get("selection_id"): row.get("state") for row in selections}
    verifier_actions = [action for action in actions
                        if assignments[action["assignment_id"]]["requirements"].get("operation") == "verify"
                        and selection_state_by_id.get(action.get("selection_id")) == "consumed"]
    semantic_by_action = {item.get("action_id"): item for item in semantic}
    verifier_action_ids = {action["action_id"] for action in verifier_actions}
    failed_verifier_ids = {item["action_id"] for item in evidence_failures
                           if item["stage"] in {"verifier_evaluation", "assignment_evidence"}}
    missing_verifier_evidence = (verifier_action_ids - set(semantic_by_action)) - failed_verifier_ids
    if (len(semantic_by_action) != len(semantic)
            or not set(semantic_by_action).issubset(verifier_action_ids)
            or (missing_verifier_evidence and termination is None)):
        raise V9ReceiptError("v9_semantic_verification_missing")
    semantic_dispositions: list[str] = []
    for action in verifier_actions:
        item = semantic_by_action.get(action["action_id"])
        if item is None:
            continue
        required = {"action_id", "input", "input_digest", "diff_digest", "test_digest",
                    "result", "evaluation"}
        if set(item) != required or item["action_id"] != action["action_id"]:
            raise V9ReceiptError("v9_semantic_verification_invalid")
        expected_input = {"provider_task": action["task"], "assignment_id": action["assignment_id"]}
        # Retained receipts bind verification to the observed current source.
        # Historical receipts keep their exact two-field input representation.
        if "source_digest" in item["input"]:
            source_digest = item["input"]["source_digest"]
            if ("local_agent_profile" not in envelope or not isinstance(source_digest, str)
                    or len(source_digest) != 64 or any(c not in "0123456789abcdef" for c in source_digest)):
                raise V9ReceiptError("v9_verifier_source_digest_invalid")
            expected_input["source_digest"] = source_digest
        if item["input"] != expected_input \
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
        semantic_dispositions.append(evaluation["disposition"])
        compared += 7
    required_verifiers = {item["assignment_id"] for item in envelope["logical_assignments"]
                          if item["requirements"].get("operation") == "verify"}
    observed_verifiers = [action["assignment_id"] for action in verifier_actions]
    all_required_pass = (bool(required_verifiers)
                         and len(observed_verifiers) == len(set(observed_verifiers))
                         and set(observed_verifiers) == required_verifiers
                         and len(semantic_dispositions) == len(required_verifiers)
                         and all(item == "valid_pass" for item in semantic_dispositions))
    if "local_agent_profile" in envelope:
        # History is fully evaluated above. A genuine failed review can be
        # superseded by repair and a fresh review; it must never poison every
        # subsequent completion or allow an old pass to approve a new edit.
        consumed_actions = [action for action in actions
                            if selection_state_by_id.get(action.get("selection_id")) == "consumed"]
        latest = {}
        for action in consumed_actions:
            key = action["assignment_id"]
            if key not in latest or action["sequence"] > latest[key]["sequence"]:
                latest[key] = action
        producer_actions = [action for action in consumed_actions
                            if assignments[action["assignment_id"]]["requirements"]["operation"] == "edit"]
        last_edit = max((action["sequence"] for action in producer_actions), default=0)
        latest_reviews = [latest.get(identity) for identity in required_verifiers]
        failed_ids = {failure["action_id"] for failure in evidence_failures}
        all_required_pass = (bool(required_verifiers)
            and all(action is not None and action["sequence"] > last_edit
                    and action["action_id"] not in failed_ids
                    and semantic_by_action.get(action["action_id"], {}).get("evaluation", {}).get("disposition") == "valid_pass"
                    for action in latest_reviews)
            and all(action["action_id"] not in failed_ids for identity, action in latest.items()
                    if assignments[identity]["requirements"]["operation"] in {"edit", "collect"}))
        observed_by_action = {item["action_id"]: item["evidence"] for item in observations}
        current_source = None
        for action in sorted(producer_actions, key=lambda item: item["sequence"]):
            if action["action_id"] in hosted_by_action:
                current_source = hosted_by_action[action["action_id"]]["source_digest"]
            for tool in observed_by_action.get(action["action_id"], {}).get("tool_observations", []):
                result = tool.get("result", {})
                if tool.get("name") == "write_file" and result.get("status") == "written":
                    current_source = result.get("source_digest")
        source_bound = (isinstance(current_source, str) and len(current_source) == 64
                        and all(char in "0123456789abcdef" for char in current_source))
        for action in latest_reviews:
            if action is None:
                source_bound = False
                continue
            item = semantic_by_action.get(action["action_id"], {})
            if "source_digest" in item.get("input", {}):
                source_bound = source_bound and item["input"]["source_digest"] == current_source
            if action["selection_decision"]["selected_binding"]["provider"] in {"claude", "codex"}:
                # Hosted verification remains bound to the Flow-observed diff
                # and tests above, after the latest source edit. Native tool
                # observations are required only for actual local selections.
                source_bound = source_bound and item.get("input", {}).get("source_digest") == current_source
                continue
            review = (item.get("result") or {}).get("current_source_review")
            observed_reviews = [tool.get("result", {}) for tool in
                observed_by_action.get(action["action_id"], {}).get("tool_observations", [])
                if tool.get("name") == "submit_review" and tool.get("result", {}).get("status") == "review_recorded"]
            actual = observed_reviews[-1] if observed_reviews else None
            test = review.get("test_evidence", {}) if isinstance(review, dict) else {}
            try:
                output_candidate = json.loads((item.get("result") or {}).get("output", ""))
            except (TypeError, ValueError):
                output_candidate = None
            source_bound = source_bound and (
                isinstance(review, dict) and isinstance(actual, dict)
                and {key: value for key, value in actual.items() if key != "status"} == review
                and output_candidate == review.get("candidate")
                and review.get("source_digest") == current_source
                and test.get("source_digest") == current_source
                and test.get("current_source_digest") == current_source
                and test.get("status") == "passed")
        # A latest producer must have actual parent observations; old source
        # writes from an earlier delegation cannot certify an unobserved turn.
        required_workers = {identity for identity, assignment in assignments.items()
                            if assignment["requirements"]["operation"] in {"edit", "collect"}}
        source_bound = source_bound and required_workers.issubset(latest)
        for identity in required_workers:
            action = latest.get(identity)
            body = observed_by_action.get(action["action_id"], {}) if action else {}
            if action and action["selection_decision"]["selected_binding"]["provider"] in {"claude", "codex"}:
                if assignments[identity]["requirements"]["operation"] == "edit":
                    source_bound = source_bound and action["action_id"] in hosted_by_action
                continue
            if not body:
                source_bound = False
            elif assignments[identity]["requirements"]["operation"] == "edit":
                source_bound = source_bound and any(
                    tool.get("name") == "write_file" and tool.get("result", {}).get("status") == "written"
                    for tool in body.get("tool_observations", []))
        all_required_pass = all_required_pass and source_bound
    if outcome["status"] in {"completed", "failed"}:
        if (outcome["status"] == "completed") != all_required_pass:
            raise V9ReceiptError("v9_outcome_semantic_mismatch")
        if outcome["status"] == "failed" and not evidence_failures \
                and not any(item != "valid_pass" for item in semantic_dispositions):
            refusal_exhaustion = (outcome["reason"] == "provider_candidates_exhausted"
                                  and bool(terminal_refusal_exhaustions))
            if not refusal_exhaustion:
                raise V9ReceiptError("v9_failed_outcome_evidence_missing")
    expected_digest = digest({key: value for key, value in receipt.items() if key != "receipt_digest"})
    if receipt.get("receipt_digest") != expected_digest:
        raise V9ReceiptError("v9_receipt_digest_mismatch")
    return {"schema_version": 1, "execution_protocol_version": 9, "status": "valid_pass",
            "compared": compared, "receipt_digest": expected_digest}


def seal_selection_receipt(envelope: dict[str, Any], actions: list[dict[str, Any]],
                           selections: list[dict[str, Any]], *,
                           provider_refusals: list[dict[str, Any]] | None = None,
                           semantic_verification: list[dict[str, Any]] | None = None,
                           evidence_failures: list[dict[str, Any]] | None = None,
                           local_agent_observations: list[dict[str, Any]] | None = None,
                           hosted_scope_observations: list[dict[str, Any]] | None = None,
                           termination: dict[str, Any] | None = None,
                           outcome: dict[str, str]) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "execution_protocol_version": 9,
        "envelope": envelope,
        "actions": actions,
        "selections": selections,
        "provider_refusals": provider_refusals or [],
        "semantic_verification": semantic_verification or [],
        "evidence_failures": evidence_failures or [],
    }
    if termination is not None:
        receipt["termination"] = termination
    if local_agent_observations is not None:
        receipt["local_agent_observations"] = local_agent_observations
    if hosted_scope_observations is not None:
        receipt["hosted_scope_observations"] = hosted_scope_observations
    receipt["outcome"] = outcome
    receipt["receipt_digest"] = digest(receipt)
    verify_selection_receipt(receipt)
    return receipt


def receipt_from_snapshot(snapshot: dict[str, Any], *, termination: dict[str, Any] | None = None,
                          outcome: dict[str, str] | None = None) -> dict[str, Any]:
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
            "prior_retryable_failures": item["decision"].get("prior_retryable_failures", []),
        })
    provider_refusals = []
    for item in snapshot.get("actions", []):
        if item.get("status") != "observed_not_executed":
            continue
        observation = (item.get("result") or {}).get("result")
        request = item.get("request") or {}
        if not isinstance(observation, dict):
            raise V9ReceiptError("v9_snapshot_provider_refusal_missing")
        provider_refusals.append({"action_id": item.get("action_id"),
                                  "selection_id": request.get("selection_id"), **observation})
    action_results = {item["action_id"]: (item.get("result") or {}).get("result")
                      for item in snapshot.get("actions", [])}
    local_observations = [{"action_id": action_id, "evidence": result["local_agent_observations"],
                           "evidence_digest": digest(result["local_agent_observations"])}
                          for action_id, result in action_results.items()
                          if isinstance(result, dict) and "local_agent_observations" in result]
    hosted_observations = [{"action_id": action_id, "evidence": result["scoped_edit"],
                            "evidence_digest": digest(result["scoped_edit"])}
                           for action_id, result in action_results.items()
                           if isinstance(result, dict) and "source_digest" in result.get("scoped_edit", {})]
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
    evidence_failures = []
    for event in snapshot.get("events", []):
        if event.get("event") != "v9_evidence_failed":
            continue
        try:
            detail = json.loads(event["detail"])
        except (TypeError, ValueError) as exc:
            raise V9ReceiptError("v9_snapshot_evidence_failure_invalid") from exc
        evidence_failures.append({"action_id": event.get("action_id"),
                                  "stage": detail.get("stage"), "detail": detail.get("detail")})
    if outcome is None and termination is not None:
        outcome = {"status": termination["status"], "reason": termination["cause"]}
    if outcome is None:
        raise V9ReceiptError("v9_outcome_missing")
    return seal_selection_receipt(envelope, actions, rows, provider_refusals=provider_refusals,
                                  semantic_verification=semantic,
                                  evidence_failures=evidence_failures,
                                  local_agent_observations=(local_observations if "local_agent_profile" in envelope else None),
                                  hosted_scope_observations=hosted_observations or None,
                                  termination=termination, outcome=outcome)


def verify_selection_receipt_snapshot(receipt: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Verify a v9 receipt and its exact ledger-derived closure."""
    result = verify_selection_receipt(receipt)
    expected = receipt_from_snapshot(snapshot, termination=receipt.get("termination"),
                                     outcome=receipt.get("outcome"))
    for field in ("envelope", "actions", "selections", "provider_refusals", "semantic_verification", "evidence_failures", "outcome", "local_agent_observations", "hosted_scope_observations"):
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
