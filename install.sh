#!/usr/bin/env bash
# flow — portable bootstrap installer
#
# Installs the latest tagged release of flow into ~/.flow in release mode.
# After running this you can delete any working clone you used; the install
# is self-contained.
#
# Idiomatic invocation:
#   curl -fsSL https://raw.githubusercontent.com/andyconley/flow/main/install.sh | bash
#
# What this does:
#   1. Queries the configured flow remote for the latest semver tag.
#   2. Shallow-clones that tag into a temporary directory.
#   3. Delegates to that clone's install-flow.sh --release, which copies the
#      framework content into ~/.flow/source/, writes the launcher to
#      ~/.local/bin/flow, and stamps install metadata into ~/.flow/config.toml.
#   4. Cleans up the temporary clone.
#
# Maintainers / contributors who want to edit framework content themselves
# should clone the repo and run ./install-flow.sh --develop instead — this
# bootstrap is specifically the consumer path.

set -euo pipefail

REPO_URL="${FLOW_REPO_URL:-https://github.com/andyconley/flow.git}"

err() { echo "error: $*" >&2; exit 1; }
info() { echo ">> $*"; }

command -v git >/dev/null 2>&1 || err "git is required but not installed"

info "querying ${REPO_URL} for the latest release..."
# Match strict semver tags only (no pre-release / +build suffixes). Sort by
# `sort -V` (version sort), pick the highest.
latest_tag="$(
  git ls-remote --tags --refs "${REPO_URL}" 2>/dev/null \
    | awk '{print $2}' \
    | sed 's|refs/tags/||' \
    | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
    | sort -V \
    | tail -n1 \
    || true
)"
[[ -n "${latest_tag}" ]] || err "no semver tags (vN.N.N) found at ${REPO_URL}"
info "latest release: ${latest_tag}"

tmp_dir="$(mktemp -d -t flow-install-XXXXXX)"
trap 'rm -rf "${tmp_dir}"' EXIT

info "downloading ${latest_tag} into a temporary directory..."
git clone --depth 1 --branch "${latest_tag}" --quiet "${REPO_URL}" "${tmp_dir}/flow"

info "running install-flow.sh --release..."
# Pass the resolved tag through explicitly so install-flow.sh stamps that
# exact version, even if multiple tags reference the cloned commit.
FLOW_VERSION_OVERRIDE="${latest_tag}" bash "${tmp_dir}/flow/install-flow.sh" --release

echo
echo "flow ${latest_tag} installed. Next steps:"
echo "  flow setup machine"
echo "  flow setup user"
echo
echo "After that, /flow-* slash commands are active in every Claude session."
echo "Run \`flow update\` to roll forward to newer tagged releases later."
