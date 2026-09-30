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
