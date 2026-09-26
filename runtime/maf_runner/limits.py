"""Hard ceilings of the stock Magentic runner.

Flow's contract validation, envelope validation, supervisor guards, and the
runner itself all read these values, so a sealed charter can never grant more
than the runner will execute. Standard library only: ``cli/`` loads this file
by path, outside the MAF interpreter.
"""

MAX_MANAGER_CALLS = 12
MAX_MANAGER_ROUNDS = 6
# One Magentic action is one delegation; paid worker calls are a subset.
MAX_ACTIONS = 6
MAX_VERIFIER_CALLS = 2
MAX_CONCURRENT = 3
MAX_REPLANS = 2
