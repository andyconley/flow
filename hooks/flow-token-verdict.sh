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
# Missing flow = silent no-op: the hook must never break a Stop.
FLOW="$HOME/.local/bin/flow"
if [ ! -x "$FLOW" ]; then
    FLOW="$(command -v flow 2>/dev/null)" || exit 0
fi
[ -n "$FLOW" ] && [ -x "$FLOW" ] || exit 0
exec "$FLOW" cost verdict --hook
