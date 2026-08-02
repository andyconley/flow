# flow CLI Reference

## Overview

`flow` manages three things:

- machine-local install support
- project-local `.flow` scaffolding
- runtime adapter generation and drift detection

## Command Reference

### `flow setup machine`

Prepare machine-local support under `~/.flow`.

Creates:

- `~/.flow/config.toml`
- `~/.flow/hooks/`
- `~/.flow/user/`
- `~/.flow/logs/`

Use this when setting up a new machine or repairing a missing local install surface.

### `flow setup project`

Scaffold `repo/.flow` into the current repository.

Behavior:

- copies template files from `scaffolds/default/`
- does not overwrite files that already exist

Use this when bootstrapping a repo for the first time.

### `flow setup user`

Install flow at the **user level** so it is active in every Claude session regardless of cwd.

Behavior:

- runs `flow sync claude --user` and `flow sync codex --user` in sequence
- generates `~/.claude/skills/flow-*/`, `~/.claude/agents/*.md`, `~/.claude/hooks/flow-*.sh`
- merges flow hook entries into `~/.claude/settings.json` (preserves unmanaged settings)
- writes `~/.claude/flow.managed.toml` and `~/.codex/flow.managed.toml` for drift tracking

Use this once per machine, then again whenever the framework scaffold changes and you want the user-level surface to follow.

### `flow refresh project`

Copy only missing files from the current framework template into an existing `repo/.flow`.

Behavior:

- adds newly introduced framework files
- leaves existing project files untouched

Use this when the framework has grown new files and a project should pick them up without replacing local edits.

### `flow bootstrap`

Validate that the minimum `repo/.flow` structure exists.

Checks for:

- `flow.toml`
- `FRAMEWORK.md`
- `PROJECT.md`
- `commands/`
- `agents/`
- `standards/`
- `project/`
- `memory/`
- `templates/`

Use this after scaffold or when diagnosing a broken repo state.

### `flow doctor`

Report machine, install, user-level, and project-level state in one output.

Current sections:

- **machine** — Python, flow home, source path, scaffold availability, config, launcher
- **install** — install mode (develop or release), version (release only), source target (develop only), installed_at timestamp
- **user-level** — Claude/Codex sync state and drift for `~/.claude/`, `~/.agents/skills/`, and `~/.codex/`
- **project** — repo `.flow/` presence, manifest, Claude/Codex sync state and drift for the current repo

Use this as the main diagnostics command.

### `flow install --release`

Convert the current install from develop mode (symlink) to release mode (real copied directory). The clone is **not** deleted — the user controls its lifecycle.

Behavior:

- Resolves the symlink target as the source clone
- Determines version via `git describe` in the clone (exact tag → base tag + dev sha → `main@<sha>`)
- Copies the release roster (`cli/`, `scaffolds/`, `hooks/`, `scripts/`, `docs/`, `README.md`) into a staging directory under `~/.flow/`
- Validates staging (must contain `cli/flow.py` and `scaffolds/default/flow.toml`)
- Atomically swaps the staging directory into `~/.flow/source/`
- Updates `~/.flow/config.toml` with `mode = "release"`, version, remote, and installed_at

Use this when a contributor's machine is ready to switch off development mode and pin to a specific version.

### `flow install --develop <clone-path>`

Convert the current install from release mode (copied directory) to develop mode (symlink to a clone).

Behavior:

- Validates that `<clone-path>` contains `cli/flow.py`
- Removes the copied directory at `~/.flow/source/`
- Creates a symlink from `~/.flow/source` to the given clone
- Updates `~/.flow/config.toml` with `mode = "develop"`, `source_target = <clone-path>`, and installed_at

Use this when switching back to maintainer mode against a working clone.

### `flow update`

Roll forward a release install to the latest semver tag from the configured remote.

In release mode:

- Calls `git ls-remote --tags --refs` against the configured remote
- Picks the highest semver-ish tag (`vMAJOR.MINOR.PATCH[-suffix]`)
- Clones that tag into a temp directory
- Stages and validates the new content, then atomically swaps into `~/.flow/source/`
- Updates `~/.flow/config.toml` with the new version and installed_at

In develop mode: prints the manual `git pull` + `flow sync ... --user` commands; takes no other action.

Flags:

- `--check` — report current vs latest version without applying. When a newer version is available, also fetches `CHANGELOG.md` from the remote at the new tag (via a sparse partial-clone — only the one file is actually downloaded) and prints the `## [<version>]` section so you can see what's in the available release. Falls back silently if no CHANGELOG entry exists for that version.
- `--resync` — after applying, also run `flow sync claude --user` and `flow sync codex --user`
- `--remote URL` — override the remote configured in `~/.flow/config.toml` (useful for testing)

The update is atomic: staging is validated before any rename happens, so a failed clone, broken staging, or swap error leaves the existing install intact. A successful update keeps no rollback state — to revert, run `flow update --remote <url>` against an older tag or re-run `install-flow.sh --release` from a checkout at the desired version.

### `flow sync claude`

Generate the Claude runtime adapter surface from `repo/.flow`.

Current outputs:

- `.claude/skills/...`
- `.claude/agents/...`
- `.claude/hooks/...`
- `.claude/settings.json`
- `.claude/flow.managed.toml`

### `flow sync claude --check`

Report Claude runtime drift without writing files.

Use this when:

- checking whether generated Claude artifacts are current
- validating CI or pre-review state
- diagnosing local manual drift

### `flow sync codex`

Generate the Codex runtime adapter surface from `repo/.flow`.

Current outputs:

- `.agents/skills/...`
- `.codex/flow.managed.toml`

### `flow sync codex --check`

Report Codex runtime drift without writing files.

### `flow sync <target> --user`

Generate the runtime adapter surface at the **user level** (`~/.claude/`, `~/.agents/skills`, and `~/.codex/flow.managed.toml`) from the framework scaffold directly. Combine with `--check` to detect drift without writing.

User-mode differences from project-mode:

- source files come from the framework scaffold (`~/.flow/source/scaffolds/default/`), not from a project's `.flow/`
- output goes to the runtime's user-level locations (universal across every session)
- hook commands in `settings.json` use `$HOME` instead of `$CLAUDE_PROJECT_DIR`
- the managed manifest's `source` fields reference the scaffold path (e.g., `~/.flow/source/scaffolds/default/commands/flow-boot.md`)
- if `~/.flow/user/flow.toml` exists, the user overlay merges on top of the framework manifest before generation: same-name commands/agents override the framework entry, new names append. User-origin entries in the managed manifest carry `~/.flow/user/...` source paths so origin is auditable. See `docs/architecture.md` "User Overlay" for the merge semantics.

Use `flow setup user` for the initial install; use `flow sync <target> --user` to re-sync after framework changes.

## Typical Sequences

### First-time local install

```bash
cd ~/personal/flow
./install-flow.sh                  # develop mode (default)
# or: ./install-flow.sh --release  # release mode — clone is disposable after install
flow setup machine
flow setup user        # installs flow at user level — active in every Claude session
```

### Release-mode framework roll-forward

```bash
flow update --check    # see what's available
flow update            # apply atomically
flow update --resync   # apply + re-sync user-level adapters
```

### First-time project bootstrap (only for repos where you want a project overlay)

```bash
cd /path/to/project
flow setup project
flow bootstrap
flow sync claude
flow sync codex
flow doctor
```

### Framework update roll-forward

```bash
cd /path/to/project
flow refresh project
flow bootstrap
flow sync claude
flow sync codex
```

### Drift-only check

```bash
flow sync claude --check
flow sync codex --check
flow doctor
```

## Failure Modes

### Missing `.flow/`

Symptom:

- `flow bootstrap` or `flow sync ...` reports that the repo is missing `.flow`

Fix:

- run `flow setup project`

### Missing manifest

Symptom:

- `flow sync ...` reports missing `.flow/flow.toml`

Fix:

- restore or refresh the project scaffold

### Unmanaged conflict

Symptom:

- sync reports unmanaged conflicts and stops

Meaning:

- a target runtime file exists, differs from generated content, and is not marked as previously flow-managed

Fix:

- move the real source change into `repo/.flow`
- or remove/rename the conflicting unmanaged runtime file
- then rerun sync

### Stale generated files

Symptom:

- `flow sync ... --check` reports drift

Fix:

- rerun the matching sync command without `--check`

## Install Scripts

flow ships two install scripts at the repo root:

- `install.sh` — portable curl-able bootstrap, primary consumer path
- `install-flow.sh` — direct installer used by the bootstrap (and by maintainers running from a clone)

### `install.sh` (portable bootstrap, consumer path)

```bash
curl -fsSL https://raw.githubusercontent.com/andyconley/flow/main/install.sh | bash
```

This script (added in v0.4.4):

- queries the configured flow remote (`https://github.com/andyconley/flow.git` by default, override via `FLOW_REPO_URL`) for the highest semver tag
- shallow-clones that tag into a temporary directory
- delegates to that clone's `install-flow.sh --release` with `FLOW_VERSION_OVERRIDE=<tag>` so the install metadata records the exact tag the user asked for, even when multiple tags reference the cloned commit
- cleans up the temporary clone on exit

Use this when:

- a first-time install where the consumer doesn't want to keep a clone
- you want the latest released version without thinking about it

Requires `git` on the consumer's `PATH`. Public hosting of the curl URL requires the flow repo to be publicly readable; against a private repo, run `bash install.sh` from a local clone instead (the script's logic works either way once it can reach the remote).

### `./install-flow.sh [--develop|--release]`

This script:

- creates `~/.flow/source` — either a symlink to the checkout (`--develop`, default) or a real copied directory (`--release`)
- writes the launcher to `~/.local/bin/flow`
- writes `~/.flow/config.toml` with `[flow]` and `[install]` sections (mode, version for release, source_target for develop, installed_at)

Modes:

- `--develop` (default) — symlinks `~/.flow/source` to the current checkout. Maintainer-shaped: edits in the clone go live immediately.
- `--release` — copies the framework into `~/.flow/source/` as a real directory using a **blacklist-based roster** (v0.6.1+): every non-dotfile top-level entry of the checkout is included except `tests/`, `install-flow.sh`, `install.sh`, plus the recursive cleanup of `__pycache__/`, `.agents/`, `.claude/`, `.codex/`, `.git/`, `*.pyc`, `.DS_Store`. New top-level files added in future versions are picked up automatically. The clone becomes disposable. Version is derived via `git describe` in the checkout, or via `FLOW_VERSION_OVERRIDE` if set.

Use this when:

- first installing `flow` directly from a clone (maintainer flow)
- moving the framework repo
- repairing the local launcher
- switching to release mode for a non-contributor install

After install, `flow update` is the canonical roll-forward path for release mode. `flow install --release` / `flow install --develop <path>` converts between modes without re-running `install-flow.sh`.
