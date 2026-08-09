# flow File Structure

## Top-Level Repo Layout

The main `flow` repo currently uses this structure:

```text
flow/
  cli/
    flow.py            entrypoint: argparse declaration and dispatch
    codex_collector.py Codex session transcripts -> usage store raw layer
    diagnostics.py     doctor, help, bootstrap
    flowtoml.py        TOML reading
    fsutil.py          filesystem primitives
    harvest.py         thin CLI wrapper around the harness collectors
    lifecycle.py       two-mode install, release staging, update
    normalize.py       turn_raw -> turn_norm, one convention across harnesses
    paths.py           machine paths and mode constants
    render.py          generated-adapter rendering
    setup.py           machine / project / user setup and refresh
    sync.py            the sync engine
    usage_store.py     SQLite store for harvested harness usage
  data/
    harness_capabilities.json
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

Flat sibling modules, not a package — the launcher runs `cli/flow.py` as a
script, which is what puts `cli/` on `sys.path` and lets the modules import each
other by bare name.

- `flow.py` — the entrypoint. Argparse declaration and dispatch only; it holds
  no command implementations and no constants.
- `paths.py`, `flowtoml.py`, `fsutil.py` — leaves. They import nothing from
  their siblings, which is what keeps the module graph acyclic.
- `render.py` — builds the text of generated adapters. Touches no filesystem.
- `sync.py` — resolves manifests, computes desired adapter output, reconciles
  it against disk.
- `setup.py` — machine, project, and user setup, plus project refresh.
- `lifecycle.py` — two-mode install, release staging, and update.
- `diagnostics.py` — `doctor`, `help`, `bootstrap`. Reports; never writes.
- `usage_store.py` — SQLite store for harvested harness usage.
- `codex_collector.py` — reads Codex session transcripts into the store's raw
  layer. Pure: no argparse, no printing, every path passed in explicitly.
- `harvest.py` — the thin CLI wrapper around collector modules (`codex_collector.py`
  today, a `claude_collector.py` sibling later). Argument resolution and
  printing live here; parsing and persistence live in each collector.
- `normalize.py` — projects `turn_raw` into `turn_norm` in one shared,
  harness-neutral convention. A separate command from `harvest`: appending new
  raw data and recomputing derived data have different cost profiles, and a
  rule change can touch every row.

Edit the module that owns the behavior. `flow.py` changes only when a command
is added, removed, or its arguments change.

`cli/` imports only the standard library and its own siblings today, and flow
ships no dependency installer, so anything added would have to be installed by
hand. That is a design choice rather than a constraint the tooling imposes —
release staging validation checks that every module-scope import *resolves*,
against the staged tree or the environment, without needing to know which
category a name belongs to. See `_validate_staging` in `cli/lifecycle.py`.

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

- `cli/*.py` for CLI behavior — the module that owns it, per the `cli/` section above
- `scaffolds/default/flow.toml` for runtime adapter policy
- `scaffolds/default/commands/*.md` for workflow source contracts
- `scaffolds/default/agents/*.md` for role source contracts
- `scaffolds/default/standards/*.md` for reusable standards
- `hooks/*.sh` for reusable runtime hook behavior
- `docs/*.md` for maintainer documentation

## What Not To Treat As Source Of Truth

Do not treat generated runtime folders as the primary source of truth at any scope:

- `<repo>/.claude/`, `<repo>/.agents/skills/`, and `<repo>/.codex/` — project-level adapter outputs derived from `<repo>/.flow/`
- `~/.claude/`, `~/.agents/skills/`, and `~/.codex/` — user-level adapter outputs derived from this repo's `scaffolds/default/`

All of these are generated. To change them, edit the corresponding source:

- For user-level outputs: edit `scaffolds/default/*` in this repo and rerun `flow sync claude --user` / `flow sync codex --user`
- For project-level outputs: edit `<repo>/.flow/*` in the consuming repo and rerun `flow sync claude` / `flow sync codex` there

## Install Scopes At A Glance

| Scope | Source | Generated to | Purpose |
|---|---|---|---|
| **User-level** | `scaffolds/default/` (this repo) **plus** `~/.flow/user/` if present | `~/.claude/`, `~/.agents/skills/`, `~/.codex/` | Framework + personal overrides active in every supported runtime session |
| **Project-level** | `<repo>/.flow/` | `<repo>/.claude/`, `<repo>/.agents/skills/`, `<repo>/.codex/` | Per-project overlay with project-specific role assignments, memory, runs |

User-level and project-level are independent — a single repo can run both, with the project overlay supplying repo-specific context layered on top of the universally-active framework.

### User overlay layout (`~/.flow/user/`)

The user overlay mirrors `scaffolds/default/`'s shape:

```text
~/.flow/user/
  flow.toml              — registers user-authored commands and agents
  agents/<name>.md       — overriding or new agents
  commands/<name>.md     — overriding or new commands
  standards/<name>.md    — overriding or new standards (runtime-resolved)
  templates/<name>.md    — overriding or new templates (runtime-resolved)
```

Commands and agents merge at `flow sync ... --user` time via `merge_user_overlay` — same name = override, new name = addition. Standards and templates aren't merged at sync time; they're resolved at runtime by the order project overlay > user overlay > framework default (see `FRAMEWORK.md` "Overlay resolution for standards and templates"). See `docs/architecture.md` for the full description.
