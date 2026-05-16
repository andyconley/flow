# Runtime Adapters

## Purpose

Runtime adapters let `flow` keep durable source content runtime-neutral while generating runtime-specific surfaces elsewhere.

The core pattern is:

- write durable source content once (in the framework scaffold for the HOW; in project overlays for the WHAT)
- generate runtime-specific wrappers and outputs per target, per scope
- track generated ownership with a managed manifest

## Install Scopes

Each runtime target can be generated at two scopes:

| Scope | Source of truth | Generated to | When to use |
|---|---|---|---|
| **User-level** | Framework scaffold (`~/.flow/source/scaffolds/default/`) **plus** user overlay (`~/.flow/user/`) when present | `~/.claude/`, `~/.codex/` | Always — installs flow framework into every Claude session |
| **Project-level** | Project overlay (`<repo>/.flow/`) | `<repo>/.claude/`, `<repo>/.codex/` | Per-repo, when you want project-specific role assignments, memory, and run artifacts |

User-mode sync (`flow sync claude --user`) and project-mode sync (`flow sync claude`) generate distinct artifacts to distinct locations and are independent. A single repo can have both active simultaneously — the user-level install provides the universal framework while the project overlay provides repo-specific context.

Mode-specific differences:

- **Hook command paths**: user-mode uses `$HOME/.claude/hooks/flow-*.sh`; project-mode uses `$CLAUDE_PROJECT_DIR/.claude/hooks/flow-*.sh`
- **Managed manifest `source` fields**: user-mode references the scaffold path (`~/.flow/source/scaffolds/default/commands/flow-boot.md`); project-mode references `.flow/commands/flow-boot.md`. User-overlay entries in user mode reference `~/.flow/user/...` so origin is auditable.
- **Settings merge target**: user-mode merges into `~/.claude/settings.json`; project-mode merges into `<repo>/.claude/settings.json`
- **User overlay** (user mode only, v0.6.0+): if `~/.flow/user/flow.toml` exists, its `[[claude.commands]]`, `[[claude.agents]]`, and `[[codex.commands]]` entries layer on top of the framework manifest before adapter generation. Same-name entries override; new names append. See `docs/architecture.md` "User Overlay" for the merge semantics. Standards and templates aren't merged at sync time — they follow the runtime resolution convention documented in `FRAMEWORK.md`.

## Current Targets

## Claude

Claude is currently the richer runtime target.

`flow sync claude` generates:

- `.claude/skills/<flow-command>/SKILL.md`
- `.claude/agents/*.md`
- `.claude/hooks/*.sh`
- `.claude/settings.json`
- `.claude/flow.managed.toml`

### Command Mapping

Source:

- `.flow/commands/*.md`

Generated:

- `.claude/skills/<name>/SKILL.md`

Behavior:

- wraps command docs with Claude-facing skill frontmatter
- includes invocation-argument guidance
- marks the generated file with a source-of-truth reminder

### Agent Mapping

Source:

- `.flow/agents/*.md`

Generated:

- `.claude/agents/*.md`

Behavior:

- current generation mode is near-verbatim sync
- a generated marker is inserted so runtime edits can be traced back to the source

### Hook Mapping

Source:

- framework repo `hooks/*.sh`

Generated:

- `.claude/hooks/*.sh`

Current hooks:

- `flow-session-start.sh`
- `flow-managed-write-reminder.sh`

### Settings Merge

Claude settings are currently merged, not fully replaced.

Managed behavior:

- remove previously managed `flow-*` hook entries
- preserve unmanaged settings
- append current managed hook entries

This is why the Claude settings file is tracked as `sync_mode = "merge"` in the managed manifest.

## Codex

Codex is currently the narrower runtime target.

`flow sync codex` generates:

- `.codex/skills/<flow-command>/SKILL.md`
- `.codex/flow.managed.toml`

### Why It Is Narrower

This is intentional.

Reasons:

- command skills map cleanly to Codex today
- the framework does not yet have a mature Codex-specific contract for hooks, settings, or generated agents
- generating fewer surfaces is better than inventing unstable abstractions

## Managed Manifests

Each runtime has a managed manifest:

- `.claude/flow.managed.toml`
- `.codex/flow.managed.toml`

These manifests record:

- target runtime
- source manifest
- managed file paths
- file kind
- source path
- sync mode

## Sync Modes

Current sync modes:

- `replace`
  - the generated file is fully owned by `flow`
- `merge`
  - `flow` owns only the managed subset of the file and preserves unmanaged content

Current use:

- most generated files use `replace`
- Claude settings use `merge`

## Conflict Rules

If a target file:

- exists
- differs from the generated content
- is not previously tracked as flow-managed
- is not marked mergeable

then sync stops with a conflict.

This prevents `flow` from silently overwriting user-owned runtime files.

## Drift Checks

Use:

- `flow sync claude --check`
- `flow sync codex --check`

These commands:

- compare desired outputs with current runtime files
- report updates or stale managed files
- do not write changes

## Current Limits

Current limitations of the adapter system:

- no content-aware merge for most generated files
- no richer Codex runtime surface yet
- no runtime-specific agent adaptation layer beyond Claude verbatim sync
- no project migration assistant for changing runtime contracts over time
