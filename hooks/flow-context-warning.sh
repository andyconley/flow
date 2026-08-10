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
# Missing flow = silent no-op: the hook must never block a prompt.
FLOW="$HOME/.local/bin/flow"
if [ ! -x "$FLOW" ]; then
    FLOW="$(command -v flow 2>/dev/null)" || exit 0
fi
[ -n "$FLOW" ] && [ -x "$FLOW" ] || exit 0
exec "$FLOW" cost warn --hook
