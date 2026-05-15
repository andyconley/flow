# flow File Structure

## Top-Level Repo Layout

The main `flow` repo currently uses this structure:

```text
flow/
  cli/
    flow.py
  docs/
    architecture.md
    cli-reference.md
    file-structure.md
    runtime-adapters.md
  hooks/
    flow-session-start.sh
    flow-managed-write-reminder.sh
  scripts/
  scaffolds/
    default/
      FRAMEWORK.md
      PROJECT.md
      flow.toml
      agents/
      commands/
      memory/
      project/
      runs/
      standards/
      templates/
  tests/
    test_flow.py
  install-flow.sh
  README.md
```

## What Each Area Owns

### `cli/`

Contains the main local entrypoint:

- `flow.py` implements setup, refresh, validation, and runtime sync behavior

Edit here when changing lifecycle or runtime generation behavior.

### `docs/`

Maintainer-facing project documentation.

Use this for:

- architecture decisions
- file-structure contract
- CLI usage details
- runtime adapter behavior

### `hooks/`

Reusable runtime hook scripts bundled by the framework repo.

Current hook scripts:

- `flow-session-start.sh`
- `flow-managed-write-reminder.sh`

Edit here when changing generated runtime hook behavior.

### `scripts/`

Reserved for helper scripts that support framework maintenance or runtime generation.

This is intentionally light right now.

### `scaffolds/default/`

This is the scaffold source copied into `repo/.flow`.

The important rule:

- content here becomes project-local source of truth
- content here is not itself the generated runtime surface

#### `scaffolds/default/FRAMEWORK.md`

Portable framework-level operating model.

#### `scaffolds/default/PROJECT.md`

Project overlay template for local role assignment, project-specific constraints, and deviations.

#### `scaffolds/default/flow.toml`

Machine-readable manifest describing:

- runtime targets
- generated command surfaces
- generated agent surfaces
- generated hook surfaces
- managed output files

This file is the adapter contract for runtime generation.

#### `scaffolds/default/agents/`

Reusable role definitions. These are portable role prompts and operating contracts.

#### `scaffolds/default/commands/`

Reusable workflow command definitions. These are the source contracts for generated runtime skills.

#### `scaffolds/default/standards/`

Reusable framework standards library.

The `standards/vendor/` subdirectory holds **verbatim mirrors** of external specifications that flow depends on (e.g., the Conventional Commits spec). Files under `vendor/` are upstream content and must not be hand-edited; the corresponding `flow.toml` `[standards.<name>]` block records the pinned upstream version and SHA. A maintainer script in `scripts/refresh-<topic>.py` rolls the mirror forward against new upstream releases.

#### `scaffolds/default/project/`

Project-specific overlay templates for domain, terminology, UX, integrations, and similar project-local truth.

#### `scaffolds/default/memory/`

Transient work-state placeholder (`STATE.md`). Durable project facts and decisions live in Claude Code's auto-memory at `~/.claude/projects/<project-id>/memory/`, not in `.flow/memory/`.

#### `scaffolds/default/templates/`

Reusable document templates such as handoffs, ADRs, and run summaries.

#### `scaffolds/default/runs/`

Reserved project-local execution log area.

### `tests/`

CLI-level regression tests.

Current focus:

- scaffold behavior
- runtime sync behavior
- drift detection
- doctor output

### `install-flow.sh`

Machine-local install helper.

It:

- links the framework repo into `~/.flow/source`
- writes a launcher to `~/.local/bin/flow`

Edit here when installation or launcher behavior changes.

## What To Edit Directly

Edit these directly in the `flow` repo:

- `cli/flow.py` for CLI behavior
- `scaffolds/default/flow.toml` for runtime adapter policy
- `scaffolds/default/commands/*.md` for workflow source contracts
- `scaffolds/default/agents/*.md` for role source contracts
- `scaffolds/default/standards/*.md` for reusable standards
- `hooks/*.sh` for reusable runtime hook behavior
- `docs/*.md` for maintainer documentation

## What Not To Treat As Source Of Truth

Do not treat generated runtime folders as the primary source of truth at any scope:

- `<repo>/.claude/` and `<repo>/.codex/` — project-level adapter outputs derived from `<repo>/.flow/`
- `~/.claude/` and `~/.codex/` — user-level adapter outputs derived from this repo's `scaffolds/default/`

All of these are generated. To change them, edit the corresponding source:

- For user-level outputs: edit `scaffolds/default/*` in this repo and rerun `flow sync claude --user` / `flow sync codex --user`
- For project-level outputs: edit `<repo>/.flow/*` in the consuming repo and rerun `flow sync claude` / `flow sync codex` there

## Install Scopes At A Glance

| Scope | Source | Generated to | Purpose |
|---|---|---|---|
| **User-level** | `scaffolds/default/` (this repo) | `~/.claude/`, `~/.codex/` | Framework active in every Claude session |
| **Project-level** | `<repo>/.flow/` | `<repo>/.claude/`, `<repo>/.codex/` | Per-project overlay with project-specific role assignments, memory, runs |

User-level and project-level are independent — a single repo can run both, with the project overlay supplying repo-specific context layered on top of the universally-active framework.
