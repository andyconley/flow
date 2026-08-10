#!/bin/bash
# Stop hook (both runtimes): judge whether this session should /clear or
# /compact and leave a verdict file for the statusline / warn hook to read.
#
# Fires on Stop rather than UserPromptSubmit on purpose: Stop is the moment
# you are deciding what to do next, and it doesn't sit in the path of your
# prompt. Writes a file instead of printing on purpose too — Stop-hook
# stdout is fed back into the conversation on both runtimes, which would
# mean spending tokens to say you are spending too many. All judgment lives
# in `flow cost verdict --hook` (store-backed, incremental); this script
# only locates the flow launcher and hands over stdin.
#
# NEVER exec, ALWAYS exit 0: exit code 2 means "block" on both runtimes,
# and argparse exits 2 on any usage error — reachable innocently (an older
# installed flow without this subcommand, or `flow` resolving to an
# unrelated binary). An advisory hook must never block a Stop, so flow's
# exit status and output are deliberately discarded.
FLOW="$HOME/.local/bin/flow"
if [ ! -x "$FLOW" ]; then
    FLOW="$(command -v flow 2>/dev/null)"
fi
if [ -n "$FLOW" ] && [ -x "$FLOW" ]; then
    "$FLOW" cost verdict --hook >/dev/null 2>&1
fi
exit 0
