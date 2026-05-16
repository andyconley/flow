#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOW_HOME="${HOME}/.flow"
BIN_DIR="${HOME}/.local/bin"
SOURCE_DIR="${FLOW_HOME}/source"
CONFIG_FILE="${FLOW_HOME}/config.toml"
DEFAULT_REMOTE="https://github.com/andyconley/flow.git"

MODE="develop"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --develop)
      MODE="develop"
      shift
      ;;
    --release)
      MODE="release"
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: install-flow.sh [--develop|--release]

  --develop  (default) Symlink ~/.flow/source -> this checkout. Edits in the
             checkout go live immediately. Intended for framework maintainers
             and contributors.

  --release  Copy framework content into ~/.flow/source as a real directory.
             The checkout becomes disposable; the running install is fully
             self-contained. The current commit's tag (or main@<sha> when no
             tag is present) is stamped into ~/.flow/config.toml. Use
             `flow update` after install to roll forward to newer tags.

After installation:
  flow setup machine
  flow setup user
USAGE
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "run with --help for usage" >&2
      exit 2
      ;;
  esac
done

mkdir -p "${FLOW_HOME}" "${BIN_DIR}"
# Remove the legacy framework→source rename target and any prior install at the
# current path. Works for both symlinks (develop) and directories (release).
rm -rf "${FLOW_HOME}/framework" "${SOURCE_DIR}"

installed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ "${MODE}" == "release" ]]; then
  # FLOW_VERSION_OVERRIDE lets a caller (e.g., the bootstrap install.sh)
  # pin the exact version label, preserving caller intent when the checkout
  # has multiple tags at HEAD or when version inference would otherwise be
  # ambiguous.
  if [[ -n "${FLOW_VERSION_OVERRIDE:-}" ]]; then
    version="${FLOW_VERSION_OVERRIDE}"
  elif version="$(git -C "${ROOT_DIR}" describe --tags --exact-match HEAD 2>/dev/null)"; then
    :
  elif base_tag="$(git -C "${ROOT_DIR}" describe --tags --abbrev=0 2>/dev/null)"; then
    sha="$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    version="${base_tag}+dev.${sha}"
  else
    sha="$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    version="main@${sha}"
  fi
  if origin_url="$(git -C "${ROOT_DIR}" config --get remote.origin.url 2>/dev/null)"; then
    remote="${origin_url}"
  else
    remote="${DEFAULT_REMOTE}"
  fi

  mkdir -p "${SOURCE_DIR}"
  # Blacklist-based release roster (backlog P8 fix). Copy every top-level entry
  # except dotfiles and the explicit excludes below. New top-level files added
  # to the framework in future versions are picked up automatically — no
  # roster-update needed in older clients.
  #
  # Excludes:
  #   tests/              dev-only
  #   install-flow.sh     bootstrap script — `flow update` is the post-install path
  #   install.sh          curl-able bootstrap; not part of the runtime
  #   .git, .DS_Store     dotfiles, excluded by `*` glob default
  #   __pycache__, *.pyc  pruned recursively after the copy below
  shopt -s nullglob
  for entry in "${ROOT_DIR}"/*; do
    name="$(basename "$entry")"
    case "$name" in
      tests|install-flow.sh|install.sh|__pycache__|.claude|.codex)
        continue
        ;;
    esac
    cp -R "$entry" "${SOURCE_DIR}/$name"
  done
  shopt -u nullglob

  # Drop dev-only artifacts that may have ridden along with cp -R.
  find "${SOURCE_DIR}" -type d \( -name __pycache__ -o -name .claude -o -name .codex -o -name .git \) -prune -exec rm -rf {} +
  find "${SOURCE_DIR}" -type f \( -name "*.pyc" -o -name ".DS_Store" \) -delete

  cat > "${CONFIG_FILE}" <<TOML
[flow]
source_home = "~/.flow/source"
launcher = "~/.local/bin/flow"

[install]
mode = "release"
version = "${version}"
remote = "${remote}"
installed_at = "${installed_at}"
TOML
else
  ln -s "${ROOT_DIR}" "${SOURCE_DIR}"
  cat > "${CONFIG_FILE}" <<TOML
[flow]
source_home = "~/.flow/source"
launcher = "~/.local/bin/flow"

[install]
mode = "develop"
source_target = "${ROOT_DIR}"
installed_at = "${installed_at}"
TOML
fi

cat > "${BIN_DIR}/flow" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$HOME/.flow/source/cli/flow.py" "$@"
EOF

chmod +x "${BIN_DIR}/flow"

echo "Installed flow (${MODE} mode)."
echo "Source:    ${SOURCE_DIR}"
echo "Launcher:  ${BIN_DIR}/flow"
echo "Config:    ${CONFIG_FILE}"
if [[ "${MODE}" == "release" ]]; then
  echo "Version:   ${version}"
fi
echo
echo "Make sure ${BIN_DIR} is on your PATH."
