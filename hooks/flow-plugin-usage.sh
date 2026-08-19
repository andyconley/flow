#!/bin/bash
# SessionStart hook (Claude only): sample the harness's plugin and skill usage
# counters into flow's store, so "which of these do I actually use" becomes a
# question with recorded history behind it rather than a guess.
#
# SessionStart rather than Stop, and the reason is cost, not freshness. The
# harness rewrites ~/.claude.json continuously during a session — measured at
# roughly every few seconds — so a Stop hook's mtime guard would almost never
# skip, and it would parse a 150 KB document on every single turn. SessionStart
# fires once per session against a file that is current whenever it looks.
#
# Deliberately NOT gated on a project having a .flow directory, unlike
# flow-session-start.sh: the counters are user-level state and most sessions run
# outside a flow project. Gating it would mean recording history only from the
# handful of directories that happen to carry a manifest, which is exactly the
# scope-dependent population the store records a scan scope to avoid.
#
# NEVER exec, ALWAYS exit 0. Exit code 2 means "block" on both runtimes, and
# argparse exits 2 on any usage error — reachable innocently through an older
# installed flow that has no `plugin-usage` subcommand. Nothing here is worth
# delaying a session for, so flow's exit status and output are discarded.
FLOW="$HOME/.local/bin/flow"
if [ ! -x "$FLOW" ]; then
    FLOW="$(command -v flow 2>/dev/null)"
fi
if [ -n "$FLOW" ] && [ -x "$FLOW" ]; then
    "$FLOW" plugin-usage snapshot --hook >/dev/null 2>&1
fi
exit 0
