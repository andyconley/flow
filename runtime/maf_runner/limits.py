"""Hard ceilings of the stock Magentic runner.

Flow's contract validation, envelope validation, supervisor guards, and the
runner itself all read these values, so a sealed charter can never grant more
than the runner will execute. Standard library only: ``cli/`` loads this file
by path, outside the MAF interpreter.
"""

MAX_MANAGER_CALLS = 12
MAX_MANAGER_ROUNDS = 6
# Manager history crosses both the child protocol and the provider adapter.
# Keep one shared ceiling so the child cannot reject a prompt the parent is
# explicitly prepared to validate and send.
MAX_MANAGER_MESSAGES_BYTES = 256 * 1024
# One Magentic action is one delegation; paid worker calls are a subset.
MAX_ACTIONS = 6
MAX_VERIFIER_CALLS = 2
MAX_CONCURRENT = 3
MAX_REPLANS = 2
# The lineage token budget (ADR 0020): expansion headroom counts tranches, and
# the sealed budget plus every tranche stays within the absolute ceiling.
MAX_TOKEN_TRANCHES = 10
MAX_LINEAGE_TOKENS = 2_000_000

# Retained local-agent workflows use explicit task budgets, not the legacy
# one-call runner's hard ceilings. None means no count ceiling; elapsed-time
# cancellation and pressure supervision still apply. These are profile defaults,
# not requirements imposed on users.
LOCAL_CONTEXT_TOKENS = 49_152
LOCAL_OUTPUT_TOKENS = 12_288
LOCAL_CONTEXT_RESERVE = 2_048


def resolve_local_agent_budget(contract=None):
    """Validate a retained-agent profile without silently applying legacy caps."""
    contract = {} if contract is None else contract
    if not isinstance(contract, dict):
        raise ValueError("local agent budget must be an object")
    defaults = {
        "context_tokens": LOCAL_CONTEXT_TOKENS,
        "output_tokens": LOCAL_OUTPUT_TOKENS,
        "context_reserve": LOCAL_CONTEXT_RESERVE,
        "request_timeout_seconds": 600,
        "turn_timeout_seconds": 2400,
        "manager_calls": None, "manager_rounds": None,
        "delegations": None, "replans": None, "tool_calls": None,
        "max_stall_count": 2,
    }
    unknown = set(contract) - set(defaults)
    if unknown:
        raise ValueError("unknown local agent budget fields: " + ", ".join(sorted(unknown)))
    result = {**defaults, **contract}
    nullable = {"manager_calls", "manager_rounds", "delegations", "replans", "tool_calls"}
    for name, value in result.items():
        if value is None and name in nullable:
            continue
        if type(value) is not int or value < 1:
            raise ValueError(f"local agent budget {name} must be a positive integer" + (" or null" if name in nullable else ""))
    if result["output_tokens"] + result["context_reserve"] >= result["context_tokens"]:
        raise ValueError("local agent budget must reserve input context")
    return result
