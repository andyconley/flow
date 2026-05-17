#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOW_HOME="${HOME}/.flow"
BIN_DIR="${HOME}/.local/bin"
SOURCE_DIR="${FLOW_HOME}/source"
CONFIG_FILE="${FLOW_HOME}/config.toml"
DEFAULT_REMOTE="https://github.com/andyconley/flow.git"
MIN_PYTHON_VERSION="3.10"

err() { echo "error: $*" >&2; exit 1; }

append_python_candidate() {
  local candidate="$1"
  [[ -n "${candidate}" ]] || return 0
  if [[ -e "${candidate}" || "${candidate}" == */* ]]; then
    candidate="$(cd "$(dirname "${candidate}")" 2>/dev/null && pwd)/$(basename "${candidate}")"
  fi
  case ":${PYTHON_CANDIDATE_SET:-}:" in
    *:"${candidate}":*)
      return 0
      ;;
  esac
  PYTHON_CANDIDATE_SET="${PYTHON_CANDIDATE_SET:-}:${candidate}"
  PYTHON_CANDIDATES+=("${candidate}")
}

build_python_candidates() {
  PYTHON_CANDIDATES=()
  PYTHON_CANDIDATE_SET=""

  if [[ -n "${FLOW_PYTHON:-}" ]]; then
    append_python_candidate "${FLOW_PYTHON}"
  fi

  if [[ -n "${FLOW_PYTHON_CANDIDATES:-}" ]]; then
    local candidate
    IFS=':' read -r -a flow_python_candidates <<< "${FLOW_PYTHON_CANDIDATES}"
    for candidate in "${flow_python_candidates[@]}"; do
      append_python_candidate "${candidate}"
    done
    return 0
  fi

  local name
  for name in python3.13 python3.12 python3.11 python3.10 python3; do
    append_python_candidate "$(command -v "${name}" 2>/dev/null || true)"
  done

  local prefix
  for prefix in /opt/homebrew/bin /usr/local/bin; do
    for name in python3.13 python3.12 python3.11 python3.10; do
      append_python_candidate "${prefix}/${name}"
    done
  done
}

resolve_python() {
  build_python_candidates

  local candidate output status
  local -a attempted=()
  for candidate in "${PYTHON_CANDIDATES[@]}"; do
    [[ -x "${candidate}" ]] || continue
    set +e
    output="$("${candidate}" -c 'import sys; print("{}.{}.{}".format(*sys.version_info[:3])); raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null)"
    status=$?
    set -e
    if [[ ${status} -eq 0 ]]; then
      FLOW_PYTHON_BIN="${candidate}"
      FLOW_PYTHON_VERSION="${output}"
      return 0
    fi
    if [[ -n "${output}" ]]; then
      attempted+=("${candidate} (${output})")
    else
      attempted+=("${candidate} (unusable)")
    fi
  done

  {
    echo "error: flow requires Python ${MIN_PYTHON_VERSION}+ to run the CLI."
    if [[ ${#attempted[@]} -gt 0 ]]; then
      echo "checked:"
      printf '  - %s\n' "${attempted[@]}"
    else
      echo "checked: no runnable Python interpreters were found on PATH or in common Homebrew locations."
    fi
    echo
    echo "Install Python ${MIN_PYTHON_VERSION}+ and rerun the installer."
    echo "On macOS with Homebrew, a typical fix is:"
    echo "  brew install python@3.12"
    echo
    echo "If you already have a compatible interpreter, point flow at it explicitly:"
    echo "  FLOW_PYTHON=/absolute/path/to/python3.12 ./install-flow.sh --${MODE}"
  } >&2
  exit 1
}

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

resolve_python

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
python = "${FLOW_PYTHON_BIN}"
python_version = "${FLOW_PYTHON_VERSION}"

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
python = "${FLOW_PYTHON_BIN}"
python_version = "${FLOW_PYTHON_VERSION}"

[install]
mode = "develop"
source_target = "${ROOT_DIR}"
installed_at = "${installed_at}"
TOML
fi

cat > "${BIN_DIR}/flow" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${FLOW_PYTHON_BIN}" "\$HOME/.flow/source/cli/flow.py" "\$@"
EOF

chmod +x "${BIN_DIR}/flow"

smoke_output="$("${BIN_DIR}/flow" --help 2>&1 >/dev/null || true)"
if ! "${BIN_DIR}/flow" --help >/dev/null 2>&1; then
  {
    echo "error: flow installed files, but the launcher smoke test failed."
    echo "selected python: ${FLOW_PYTHON_BIN} (${FLOW_PYTHON_VERSION})"
    echo "launcher:        ${BIN_DIR}/flow"
    echo "smoke test:      ${BIN_DIR}/flow --help"
    if [[ -n "${smoke_output}" ]]; then
      echo
      echo "${smoke_output}"
    fi
    echo
    echo "If you already have another compatible interpreter, rerun with:"
    echo "  FLOW_PYTHON=/absolute/path/to/python3.12 ./install-flow.sh --${MODE}"
  } >&2
  exit 1
fi

echo "Installed flow (${MODE} mode)."
echo "Source:    ${SOURCE_DIR}"
echo "Launcher:  ${BIN_DIR}/flow"
echo "Config:    ${CONFIG_FILE}"
echo "Python:    ${FLOW_PYTHON_BIN} (${FLOW_PYTHON_VERSION})"
if [[ "${MODE}" == "release" ]]; then
  echo "Version:   ${version}"
fi
echo
echo "Make sure ${BIN_DIR} is on your PATH."
