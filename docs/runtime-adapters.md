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
| **User-level** | Framework scaffold (`~/.flow/source/scaffolds/default/`) **plus** user overlay (`~/.flow/user/`) when present | `~/.claude/`, `~/.agents/skills/`, `~/.codex/` | Always — installs Flow into every supported runtime session |
| **Project-level** | Project overlay (`<repo>/.flow/`) | retired project-local adapter output | Retired; project overlays now provide context and run artifacts, not generated runtime adapters |

Sync is user-level only (`flow sync claude --user`). Project-mode sync generated a second, repo-local copy of the same adapters from a project's own copies of the framework; it was retired along with those copies. The user-level install provides the universal framework in every session, and a repo's `.flow/` provides that project's context — the two no longer overlap.

Historical mode-specific differences:

- **Hook command paths**: Claude user-mode uses `"$HOME"/.claude/hooks/flow-*.sh`; Claude project-mode uses `"$CLAUDE_PROJECT_DIR"/.claude/hooks/flow-*.sh`. Codex user-mode uses `"$HOME"/.codex/hooks/flow-*.sh`; Codex project-mode uses `"$(git rev-parse --show-toplevel)"/.codex/hooks/flow-*.sh`.
- **Managed manifest `source` fields**: user-mode references the scaffold path (`~/.flow/source/scaffolds/default/commands/flow-boot.md`); project-mode references `.flow/commands/flow-boot.md`. User-overlay entries in user mode reference `~/.flow/user/...` so origin is auditable.
- **Settings/hooks merge target**: user-mode merges into `~/.claude/settings.json` and `~/.codex/hooks.json`; project-mode merges into `<repo>/.claude/settings.json` and `<repo>/.codex/hooks.json`.
- **User overlay** (user mode only, v0.6.0+): if `~/.flow/user/flow.toml` exists, its `[[claude.commands]]`, `[[codex.commands]]`, `[[claude.hooks]]`, `[[codex.hooks]]`, and shared `[[agents]]` entries layer on top of the framework manifest before adapter generation. Same-name entries override; new names append. See `docs/architecture.md` "User Overlay" for the merge semantics. Standards and templates aren't merged at sync time — they follow the runtime resolution convention documented in `FRAMEWORK.md`.

## Current Targets

### Claude

Claude is a native skill, agent, hook, and settings target.

`flow sync claude --user` generates:

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

- shared `[[agents]]` entries select source files and semantic model tiers
- model and effort are resolved from `flow.toml` and written into generated frontmatter
- source agent frontmatter remains the fallback for non-policy metadata such as tools and description
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

### Codex

Codex is a native skill, agent, and hook target.

`flow sync codex --user` generates:

- `.agents/skills/<flow-command>/SKILL.md`
- `.codex/agents/*.toml`
- `.codex/hooks/*.sh`
- `.codex/hooks.json`
- `.codex/flow.managed.toml`

Generated Codex skills include the required `name` and `description` YAML
frontmatter. Existing project manifests that still declare `.codex/skills`
are normalized to `.agents/skills` during sync, and previously managed legacy
files are removed without touching unmanaged files.

Generated Codex agents include:

- `name`
- `description`
- `developer_instructions` copied from the Flow agent body
- `model`
- `model_reasoning_effort`

### Model Routing

Flow uses shared semantic tiers in `flow.toml` rather than hard-coding concrete
runtime models in command prose. Runtime adapters resolve each agent's
`model_tier` into native fields:

- Claude writes `model` and `effort` into `.claude/agents/*.md`
- Codex writes `model` and `model_reasoning_effort` into `.codex/agents/*.toml`

Generated command skills also include a routing table derived from the same
policy. Treat that table as Flow's intended runtime configuration, not a proof
that the client honored it. Use `flow doctor` for static checks and the printed
manual smoke-test guidance when verifying a specific Claude or Codex client.

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

- `flow sync claude --user --check`
- `flow sync codex --user --check`
- `flow runtime smoke --target all`

These commands:

- compare desired outputs with current runtime files
- report updates or stale managed files
- do not write changes

`flow runtime smoke` goes one step further than drift checks: it verifies
freshness plus the generated command, agent, hook, managed-manifest, C-lite
protocol, and model/effort policy surfaces that local files can prove. It also
prints the manual checks still required for actual client behavior: command
discovery, role-agent invocation, and transcript/log evidence that the runtime
honored model and effort routing.

Orchestration guidance is authored once in the canonical command sources and rendered into both runtime surfaces. The generated files do not grant capabilities or prove provider identity; `confirmed`, `missing`, and `unknown` in a run's orchestration contract remain evidence declarations that the runtime cannot silently upgrade.

## Current Limits

Current limitations of the adapter system:

- no content-aware merge for most generated files
- no automated client invocation or transcript verification for whether Claude or Codex honored configured subagent models
- no project migration assistant for changing runtime contracts over time
