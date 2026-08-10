#!/bin/bash
# PostToolUse + UserPromptSubmit hook (both runtimes): the overlay-commit nudge.
#
# `FRAMEWORK.md` says the agent that edits user-overlay content commits it in
# the same turn. Nothing detected a session that didn't, so a compaction or a
# fresh session quietly regressed to piling up uncommitted work. This prints
# one advisory line when the overlay's repo has something outstanding, and
# nothing at all otherwise — including when there is no overlay repo, which
# is the default.
#
# Registered on UserPromptSubmit rather than Stop on purpose: Stop's stdout
# lands in the transcript, not in the model's context (which is why
# flow-token-verdict.sh writes a file there instead), while UserPromptSubmit's
# stdout is injected as context. The nudge therefore arrives at the start of
# the next turn, where the agent can still act on it.
#
# NEVER exec, ALWAYS exit 0: exit code 2 means "block" on both runtimes, and
# argparse exits 2 on any usage error. stdout is kept (it is the advisory
# line); stderr and the exit status are discarded — an advisory hook must
# never erase a prompt or interrupt a tool call.
FLOW="$HOME/.local/bin/flow"
if [ ! -x "$FLOW" ]; then
    FLOW="$(command -v flow 2>/dev/null)"
fi
if [ -n "$FLOW" ] && [ -x "$FLOW" ]; then
    "$FLOW" overlay check --hook 2>/dev/null
fi
exit 0
