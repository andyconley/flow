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
  templates/
    framework/
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

### `templates/framework/`

This is the scaffold source copied into `repo/.flow`.

The important rule:

- content here becomes project-local source of truth
- content here is not itself the generated runtime surface

#### `templates/framework/FRAMEWORK.md`

Portable framework-level operating model.

#### `templates/framework/PROJECT.md`

Project overlay template for local role assignment, project-specific constraints, and deviations.

#### `templates/framework/flow.toml`

Machine-readable manifest describing:

- runtime targets
- generated command surfaces
- generated agent surfaces
- generated hook surfaces
- managed output files

This file is the adapter contract for runtime generation.

#### `templates/framework/agents/`

Reusable role definitions. These are portable role prompts and operating contracts.

#### `templates/framework/commands/`

Reusable workflow command definitions. These are the source contracts for generated runtime skills.

#### `templates/framework/standards/`

Reusable framework standards library.

#### `templates/framework/project/`

Project-specific overlay templates for domain, terminology, UX, integrations, and similar project-local truth.

#### `templates/framework/memory/`

Durable project memory placeholders and conventions.

#### `templates/framework/templates/`

Reusable document templates such as handoffs, ADRs, and run summaries.

#### `templates/framework/runs/`

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

- links the framework repo into `~/.flow/framework`
- writes a launcher to `~/.local/bin/flow`

Edit here when installation or launcher behavior changes.

## What To Edit Directly

Edit these directly in the `flow` repo:

- `cli/flow.py` for CLI behavior
- `templates/framework/flow.toml` for runtime adapter policy
- `templates/framework/commands/*.md` for workflow source contracts
- `templates/framework/agents/*.md` for role source contracts
- `templates/framework/standards/*.md` for reusable standards
- `hooks/*.sh` for reusable runtime hook behavior
- `docs/*.md` for maintainer documentation

## What Not To Treat As Source Of Truth

Do not treat generated runtime folders in downstream projects as the primary source of truth:

- `.claude/`
- `.codex/`

Those are adapter outputs derived from `repo/.flow`.
