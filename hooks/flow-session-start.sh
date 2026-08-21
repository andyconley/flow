#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"

if [[ ! -d "${PROJECT_DIR}/.flow" ]]; then
  exit 0
fi

cat <<'EOF'
This project uses the flow framework.

`.flow/` holds this project's own work: its context, its transient state, and
its run artifacts. Commands, agents, standards, and templates come from the
user-level install, not from here — edit those in `~/.flow/user/` or the
framework source and rerun `flow sync claude --user`.

Primary project context lives in:
- `.flow/PROJECT.md`
- `.flow/memory/STATE.md`

An overlay set up before the scaffold was thinned may also carry copies of
framework files. `flow project audit` reports them; `flow project migrate`
removes the ones that are byte-identical to the framework's.
EOF
