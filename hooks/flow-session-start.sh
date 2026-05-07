#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"

if [[ ! -d "${PROJECT_DIR}/.flow" ]]; then
  exit 0
fi

cat <<'EOF'
This project uses the flow framework.

The portable source of truth for workflow commands, agents, standards, and memory lives under `.flow/`.
Flow-generated Claude adapters live under `.claude/` and are derived output.
If a generated Claude skill, agent, hook, or settings entry needs to change, update the corresponding `.flow` source or framework manifest and rerun `flow sync claude`.

Primary project context lives in:
- `.flow/FRAMEWORK.md`
- `.flow/PROJECT.md`
- `.flow/memory/STATE.md`
- `.flow/memory/DECISIONS.md`
EOF
