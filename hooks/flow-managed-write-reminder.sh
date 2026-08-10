#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
INPUT="$(cat)"

FILE_PATH="$(
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))' <<<"${INPUT}"
)"

case "${FILE_PATH}" in
  "${PROJECT_DIR}/.claude/skills/"*|"${PROJECT_DIR}/.claude/agents/"*|"${PROJECT_DIR}/.claude/hooks/flow-"*|"${PROJECT_DIR}/.claude/settings.json"|"${PROJECT_DIR}/.claude/flow.managed.toml")
    cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"You edited a flow-managed Claude adapter file. The durable source of truth is under `.flow/`. Port the change there and rerun `flow sync claude` before treating the update as complete."}}
EOF
    ;;
esac
