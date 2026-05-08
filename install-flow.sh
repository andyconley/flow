#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOW_HOME="${HOME}/.flow"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "${FLOW_HOME}" "${BIN_DIR}"
# Clean up legacy symlink from before the rename, plus any prior install of the new symlink
rm -rf "${FLOW_HOME}/framework" "${FLOW_HOME}/source"
ln -s "${ROOT_DIR}" "${FLOW_HOME}/source"

cat > "${BIN_DIR}/flow" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$HOME/.flow/source/cli/flow.py" "$@"
EOF

chmod +x "${BIN_DIR}/flow"

echo "Installed flow."
echo "Source:    ${FLOW_HOME}/source"
echo "Launcher:  ${BIN_DIR}/flow"
echo
echo "Make sure ${BIN_DIR} is on your PATH."
