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

Report machine, user-level, and project-level state in one output.

Current sections:

- **machine** — Python, flow home, source symlink, scaffold availability, config, launcher
- **user-level** — Claude/Codex sync state and drift for `~/.claude/` and `~/.codex/` (active in every Claude session)
- **project** — repo `.flow/` presence, manifest, Claude/Codex sync state and drift for the current repo

Use this as the main diagnostics command.

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

- `.codex/skills/...`
- `.codex/flow.managed.toml`

### `flow sync codex --check`

Report Codex runtime drift without writing files.

### `flow sync <target> --user`

Generate the runtime adapter surface at the **user level** (`~/.claude/` or `~/.codex/`) from the framework scaffold directly. Combine with `--check` to detect drift without writing.

User-mode differences from project-mode:

- source files come from the framework scaffold (`~/.flow/source/scaffolds/default/`), not from a project's `.flow/`
- output goes to `~/.claude/...` / `~/.codex/...` (universal across every Claude session)
- hook commands in `settings.json` use `$HOME` instead of `$CLAUDE_PROJECT_DIR`
- the managed manifest's `source` fields reference the scaffold path (e.g., `~/.flow/source/scaffolds/default/commands/flow-boot.md`)

Use `flow setup user` for the initial install; use `flow sync <target> --user` to re-sync after framework changes.

## Typical Sequences

### First-time local install

```bash
cd ~/personal/flow
./install-flow.sh
flow setup machine
flow setup user        # installs flow at user level — active in every Claude session
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

## Install Script

### `./install-flow.sh`

This script:

- links the framework repo into `~/.flow/source`
- writes the launcher to `~/.local/bin/flow`

Use this when:

- first installing `flow`
- moving the framework repo
- repairing the local launcher
