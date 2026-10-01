"""Protocol-v9 application boundary for logical provider binding."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Callable, TYPE_CHECKING

try:
    from execution_contracts import (
        ContractError,
        envelope_digest,
        expected_v9_logical_action_id,
        expected_v9_provider_action_id,
        validate_action,
    )
    from provider_selection import canonical_bytes, digest, select_candidate
    from selection_authority import effective_family_exclusions
except ModuleNotFoundError:  # Package import used by the MAF child.
    from .execution_contracts import (
        ContractError,
        envelope_digest,
        expected_v9_logical_action_id,
        expected_v9_provider_action_id,
        validate_action,
    )
    from .provider_selection import canonical_bytes, digest, select_candidate
    from .selection_authority import effective_family_exclusions

if TYPE_CHECKING:
    try:
        from execution_ledger import ExecutionLedger
    except ModuleNotFoundError:
        from .execution_ledger import ExecutionLedger


class SelectionDenied(ContractError):
    """The proposed binding is not the exact deterministic decision."""


class RecoveryRequired(RuntimeError):
    """Provider I/O started or may have started; fallback is forbidden."""


def assignment_for(envelope: dict[str, Any], assignment_id: str) -> dict[str, Any]:
    assignment = next((item for item in envelope["logical_assignments"]
                       if item["assignment_id"] == assignment_id), None)
    if assignment is None:
        raise SelectionDenied("logical assignment is not listed")
    return assignment


def compute_binding(envelope: dict[str, Any], assignment_id: str, *,
                    prior_no_send_failures: list[str] | None = None,
                    runtime_excluded_families: list[str] | None = None) -> dict[str, Any]:
    assignment = assignment_for(envelope, assignment_id)
    inputs = envelope["selection_inputs"]
    requirements = assignment["requirements"]
    excluded_families = (runtime_excluded_families if runtime_excluded_families is not None
                         else effective_family_exclusions(envelope, assignment_id))
    return select_candidate(
        requirements,
        inputs["policy"],
        inputs["catalog"],
        inputs["availability"],
        prior_no_send_failures=prior_no_send_failures or [],
        excluded_families=excluded_families,
    )


def bootstrap_manager(envelope: dict[str, Any]) -> dict[str, Any]:
    managers = [item for item in envelope["logical_assignments"]
                if item["requirements"].get("operation") == "manage"]
    if len(managers) != 1:
        raise SelectionDenied("protocol v9 requires exactly one logical manager assignment")
    return compute_binding(envelope, managers[0]["assignment_id"])


def make_action(envelope: dict[str, Any], assignment_id: str, task: str, *,
                sequence: int, manager_turn: int, decision: dict[str, Any] | None = None,
                selection_id: str | None = None,
                runtime_excluded_families: list[str] | None = None) -> dict[str, Any]:
    assignment = assignment_for(envelope, assignment_id)
    proposed = deepcopy(decision or compute_binding(
        envelope, assignment_id, runtime_excluded_families=runtime_excluded_families))
    task_digest = hashlib.sha256(task.encode()).hexdigest()
    action = {
        "schema_version": 1,
        "kind": "delegate",
        "attempt_id": envelope["attempt_id"],
        "envelope_digest": envelope_digest(envelope),
        "assignment_id": assignment_id,
        "role": assignment["role"],
        "task": task,
        "task_digest": task_digest,
        "sequence": sequence,
        "manager_turn": manager_turn,
        "selection_id": selection_id or digest({
            "attempt_id": envelope["attempt_id"], "assignment_id": assignment_id,
            "sequence": sequence, "decision_digest": proposed["decision_digest"],
        }),
        "selection_decision": proposed,
    }
    action["logical_action_id"] = expected_v9_logical_action_id(action)
    action["action_id"] = expected_v9_provider_action_id(action)
    return action


def authorize_and_dispatch(
    envelope: dict[str, Any], action: dict[str, Any],
    adapter_send: Callable[[dict[str, Any], dict[str, Any]], Any],
    *, readiness_recheck: Callable[[dict[str, Any]], dict[str, Any]],
    ledger: "ExecutionLedger | None" = None,
    generation: int | None = None,
    predecessor_selection_id: str | None = None,
) -> dict[str, Any]:
    """Recompute, fence readiness, and invoke exactly one selected adapter.

    Supplying a ledger is the production v9 boundary.  Legacy helper callers
    remain usable for unit construction, but runtime dispatch must supply the
    Flow-owned ledger and owner generation so no provider I/O can occur before
    a durable send claim.
    """
    validate_action(envelope, action)
    # A pre-send refusal is a durable, no-I/O fact.  Its successor is still
    # Flow-derived, but must exclude precisely the candidates already refused
    # for this logical action.  Never accept an arbitrary child-supplied list.
    prior_failures = action["selection_decision"].get("prior_no_send_failures", [])
    if (not isinstance(prior_failures, list) or any(not isinstance(item, str) or not item
                                                    for item in prior_failures)
            or len(set(prior_failures)) != len(prior_failures)):
        raise SelectionDenied("invalid predecessor no-send failures")
    runtime_families = (_runtime_family_exclusions(envelope, action["assignment_id"], ledger)
                        if ledger is not None else None)
    expected = compute_binding(envelope, action["assignment_id"],
                               prior_no_send_failures=prior_failures,
                               runtime_excluded_families=runtime_families)
    if canonical_bytes(action["selection_decision"]) != canonical_bytes(expected):
        raise SelectionDenied("child selection differs from Flow recomputation")
    binding = expected.get("selected_binding")
    if binding is None:
        raise SelectionDenied("no eligible provider candidate")
    if (ledger is None) != (generation is None):
        raise SelectionDenied("v9 send fence requires both ledger and generation")
    if ledger is not None:
        ledger.prepare_v9_selection(envelope, action, generation=generation,
                                    predecessor_selection_id=predecessor_selection_id)
    observed = readiness_recheck(deepcopy(binding))
    if not isinstance(observed, dict) or observed.get("candidate_id") != binding["candidate_id"]:
        raise SelectionDenied("readiness recheck is not bound to the selected candidate")
    if observed.get("state") != "ready":
        if observed.get("no_send_observed") is not True:
            raise RecoveryRequired("readiness failure lacks positive no-send evidence")
        if ledger is not None:
            ledger.refuse_v9_pre_send(envelope, action, generation=generation,
                                      evidence_code=observed.get("evidence_code", "pre_send_unavailable"))
        successor = compute_binding(
            envelope, action["assignment_id"],
            prior_no_send_failures=[*prior_failures, binding["candidate_id"]],
            runtime_excluded_families=runtime_families,
        )
        return {
            "status": "pre_send_refused",
            "selection_id": action["selection_id"],
            "candidate_id": binding["candidate_id"],
            "evidence_code": observed.get("evidence_code", "pre_send_unavailable"),
            "successor_decision": successor,
        }
    try:
        if ledger is None:
            result = adapter_send(deepcopy(binding), deepcopy(action))
        else:
            with ledger.v9_send_fence(envelope, action, generation=generation) as finish_send:
                result = adapter_send(deepcopy(binding), deepcopy(action))
                finish_send(result)
    except BaseException as exc:
        raise RecoveryRequired("provider send started or became uncertain") from exc
    return {
        "status": "completed",
        "selection_id": action["selection_id"],
        "candidate_id": binding["candidate_id"],
        "provider_action_id": action["action_id"],
        "result": result,
    }


def _runtime_family_exclusions(envelope: dict[str, Any], assignment_id: str,
                               ledger: "ExecutionLedger") -> list[str] | None:
    constraints = [item for item in envelope["selection_authority"]["independence_constraints"]
                   if item["assignment_id"] == assignment_id]
    if not constraints:
        return None
    if len(constraints) != 1:
        raise SelectionDenied("independent verifier requires exactly one constraint")
    constraint = constraints[0]
    required = constraint["producer_assignment_ids"] + constraint["evidence_collector_assignment_ids"]
    snapshot = ledger.snapshot(envelope["attempt_id"])
    families: list[str] = []
    for source_id in required:
        matches = [item for item in snapshot["actions"]
                   if item["request"].get("assignment_id") == source_id and item["status"] == "completed"]
        if len(matches) != 1:
            raise SelectionDenied("independent verifier lineage is incomplete")
        binding = matches[0]["request"].get("selection_decision", {}).get("selected_binding")
        family = binding.get("provider_family") if isinstance(binding, dict) else None
        if not isinstance(family, str) or not family:
            raise SelectionDenied("independent verifier lineage has no consumed provider family")
        if family not in families:
            families.append(family)
    return families
