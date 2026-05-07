#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOW_HOME="${HOME}/.flow"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "${FLOW_HOME}" "${BIN_DIR}"
rm -rf "${FLOW_HOME}/framework"
ln -s "${ROOT_DIR}" "${FLOW_HOME}/framework"

cat > "${BIN_DIR}/flow" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$HOME/.flow/framework/cli/flow.py" "$@"
EOF

chmod +x "${BIN_DIR}/flow"

echo "Installed flow."
echo "Framework: ${FLOW_HOME}/framework"
echo "Launcher:  ${BIN_DIR}/flow"
echo
echo "Make sure ${BIN_DIR} is on your PATH."
