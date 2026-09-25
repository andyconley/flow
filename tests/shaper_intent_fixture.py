"""Reviewed structured Shaper intent fixture for delivery-boundary tests."""


def shaper_intent(definition_digests=None, *, limits=None, expansion_headroom=None, max_delegations=6):
    """Return a valid intent; ``limits`` overrides enforceable values.

    The default base limits sit at the runner ceilings, so expansion tests
    lower them with ``limits`` before sealing ``expansion_headroom``.
    """
    definition_digests = definition_digests or {
        "lead-developer": "1" * 64,
        "quality-reviewer": "2" * 64,
        "test-engineer": "3" * 64,
    }
    intent = {
        "problem": "Transfer approved intent to one fenced Delivery Lead.",
        "intended_users": ["Flow maintainers and operators."],
        "outcomes": ["Seal and enforce Flow-owned delivery authority."],
        "scope": ["Canonical contracts and a bounded delivery proof."],
        "exclusions": ["No silent charter amendment."],
        "constraints": ["Flow grants every provider dispatch."],
        "assumptions": ["Runtime sessions are evidence, not authority."],
        "acceptance_criteria": ["Flow observes the producer diff, test, and independent verifier."],
        "risks": [{"risk": "runtime projection expands authority", "owner": "Flow", "status": "owned"}],
        "open_decisions": [],
        "decision_owners": [],
        "allowed_specialists": [
            {"role": role, "capabilities": capabilities, "definition_digest": definition_digests[role], "maximum_instances": 1}
            for role, capabilities in (
                ("lead-developer", ["scoped-edit"]),
                ("quality-reviewer", ["read-only-review"]),
                ("test-engineer", ["bounded-verification"]),
            )
        ],
        "prohibited_capabilities": ["silent-charter-amendment", "ungranted-provider-dispatch"],
        "delegation_matrix": {"max_delegations": 6, "delegated_expansion": False},
        "approval_matrix": {"charter_amendment": "shaper_or_engineer", "provider_dispatch": "Flow_grant", "acceptance": "Flow_gate"},
        "budget_safety_envelope": {"enforceable": {
            "max_concurrent": 3, "max_replans": 2, "runtime_seconds": 300,
            "tools": ["read", "edit", "test"], "paths": ["charter-scoped"],
            "outputs": ["diff", "test", "receipt"], "retries": 0,
            "max_manager_calls": 12, "max_manager_rounds": 6, "max_paid_worker_calls": 6,
        }, "observations": ["provider_usage_when_available"]},
        "boundaries": {"artifact_root": ".flow/runs/current", "worktree_policy": "Flow-bound"},
        "amendment_lineage": [],
        "approval_history": [{"event": "approve-definition", "authority": "engineer"}],
        "next_lane_eligibility": ["delivery"],
    }
    intent["delegation_matrix"]["max_delegations"] = max_delegations
    intent["budget_safety_envelope"]["enforceable"].update(limits or {})
    if expansion_headroom is not None:
        intent["expansion_headroom"] = expansion_headroom
        intent["delegation_matrix"]["delegated_expansion"] = any(expansion_headroom.values())
    return intent
