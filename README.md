# flow

Portable AI workflow framework.

## What It Is

`flow` is split into three layers:

- machine-local install support in `~/.flow/`
- reusable framework source in this repo
- repo-local instantiated framework in `repo/.flow`

The framework source of truth lives in `.flow/`.
Claude-facing files in `.claude/` are generated adapters.

## Current Repo Layout

- `cli/` - local CLI entrypoint
- `templates/` - repo scaffold source
- `hooks/` - reusable Claude hook scripts bundled by `flow`
- `scripts/` - setup helpers

## What Exists Now

### Framework content

The framework template now includes:

- a broad standards library under `.flow/standards/`
- richer command contracts under `.flow/commands/`
- richer role definitions under `.flow/agents/`
- project overlay templates under `.flow/project/`
- memory, templates, and run scaffolding
- a machine-readable framework manifest at `.flow/flow.toml`

### CLI lifecycle

Available commands:

```bash
flow doctor
flow setup machine
flow setup project
flow refresh project
flow bootstrap
flow sync claude
flow sync claude --check
```

What they do:

- `flow setup machine`
  - prepares `~/.flow/`, `~/.local/bin/flow`, and local config
- `flow setup project`
  - scaffolds `.flow/` into the current repo
- `flow refresh project`
  - adds newly introduced framework files into an existing `.flow/` without overwriting local edits
- `flow bootstrap`
  - validates that the required `.flow/` structure exists
- `flow doctor`
  - reports framework, repo, and Claude sync state
- `flow sync claude`
  - generates Claude adapters from `.flow/`
- `flow sync claude --check`
  - reports Claude adapter drift without writing files

### Claude adapter generation

`flow sync claude` currently generates:

- `.claude/skills/<flow-command>/SKILL.md`
  - from `.flow/commands/*.md`
- `.claude/agents/*.md`
  - from `.flow/agents/*.md`
- `.claude/hooks/*.sh`
  - from reusable hook scripts in this repo
- `.claude/settings.json`
  - with managed hook configuration merged into existing settings
- `.claude/flow.managed.toml`
  - machine-readable manifest of managed generated files

## Managed Boundaries

`flow` treats these as generated, managed surfaces:

- `.claude/skills/...`
- `.claude/agents/...`
- `.claude/hooks/flow-*.sh`
- managed hook entries inside `.claude/settings.json`
- `.claude/flow.managed.toml`

Rules:

- edit `.flow/commands/*` to change generated skills
- edit `.flow/agents/*` to change generated agents
- edit framework hook sources in this repo to change generated hook scripts
- rerun `flow sync claude` after changing the source of truth

`flow sync claude` preserves unmanaged Claude files and only removes files that were previously marked as flow-managed and are no longer desired.

## Claude Runtime Behavior

The generated Claude runtime currently includes:

- slash-command style skills for `flow-*`
- project subagents from `.flow/agents`
- a `SessionStart` hook that injects flow orientation context
- a `PostToolUse` reminder hook that nudges edits back to `.flow/` when generated Claude files are modified directly

## Smoke-Tested Behavior

The current implementation has been smoke-tested for:

- `flow setup project`
- `flow bootstrap`
- `flow sync claude`
- `flow sync claude --check`
- generated skill and agent output
- generated hook scripts and executable bits
- managed settings generation
- drift detection in `flow doctor`
- missing-file restoration in `flow refresh project`

## Local Install

```bash
./install-flow.sh
```

This installs a `flow` launcher at `~/.local/bin/flow` and links the framework repo into `~/.flow/framework`.

## Typical Flow

```bash
cd ~/src/flow
./install-flow.sh

cd /path/to/project
flow setup project
flow bootstrap
flow sync claude
flow doctor
```

## What’s Left

The framework is now usable, but it is not finished. Main gaps:

- no adapters yet for non-Claude runtimes
- no dedicated automated test suite for the `flow` CLI itself
- no content-aware upgrade path for existing project files beyond missing-file refresh
- no finer-grained managed-settings metadata beyond generated hook merging
- no project-specific migration helpers beyond the generic framework lifecycle
- no packaged release/versioning workflow yet beyond the branch structure in git

## Current Recommendation

Use `develop` as the active integration branch while the framework runtime keeps evolving.
