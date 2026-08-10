#!/bin/bash
# UserPromptSubmit hook (both runtimes): the pre-execution warning.
#
# Reads the verdict file the Stop hook last wrote — zero computation at
# prompt time — and prints one advisory line only when carry is heavy and
# has grown since the last warning. That single line is injected as context
# by the runtime, so the model AND the user see it before the next
# expensive turn; every other case prints nothing. Throttling, thresholds,
# and all judgment live in `flow cost warn --hook`.
#
# NEVER exec, ALWAYS exit 0: exit code 2 means "block the prompt" on both
# runtimes, and argparse exits 2 on any usage error. stdout is kept (it is
# the advisory line); stderr and the exit status are discarded — an
# advisory hook must never erase a prompt.
FLOW="$HOME/.local/bin/flow"
if [ ! -x "$FLOW" ]; then
    FLOW="$(command -v flow 2>/dev/null)"
fi
if [ -n "$FLOW" ] && [ -x "$FLOW" ]; then
    "$FLOW" cost warn --hook 2>/dev/null
fi
exit 0
