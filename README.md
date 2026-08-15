# flow

Portable workflow framework for AI-assisted development.

## What It Is

`flow` is a local framework for working with AI coding agents in a more deliberate way. It gives you a shared workflow, role definitions, standards, and durable artifacts so sessions do not depend on whatever context happens to be in the chat.

Flow is extensible. You can add your own commands, agents, hooks, standards, templates, and project notes without forking the framework. User overlays apply across your machine; project overlays apply only inside the repo that owns them.

Use it when you want an agent to:

- define work before planning it
- choose an approach before implementation starts
- keep implementation work gated and reviewable
- use the same role expectations across Claude and Codex
- leave behind useful state, requirements, notes, and handoffs
- get feedback on session size, token usage, and when a session should be compacted or cleared

Flow is not the project itself. It is the operating model around the project: the commands, agents, standards, templates, hooks, and local CLI that keep AI-assisted work from turning into one long unstructured chat.

For the internal architecture, see [architecture.md](docs/architecture.md).

## Current Repo Layout

- `cli/` - local CLI entrypoint
- `docs/` - maintainer docs for architecture, file structure, runtime adapters, and backlog
- `scaffolds/default/` - the framework scaffold copied into user-level installs and per-project overlays
- `hooks/` - reusable Claude hook scripts bundled by `flow`
- `scripts/` - reserved for framework maintenance helpers
- `tests/` - CLI-level regression tests

## Maintainer Docs

For maintainer-oriented documentation, start with:

- [architecture.md](docs/architecture.md)
- [file-structure.md](docs/file-structure.md)
- [cli-reference.md](docs/cli-reference.md)
- [runtime-adapters.md](docs/runtime-adapters.md)
- [backlog.md](docs/backlog.md)

## What Exists Now

### Workflow lanes

The default Flow lane is:

```text
boot -> define -> solution (optional) -> plan -> implement -> review -> archive
```

Small, narrow work can go straight to `scout`. Interrupted work resumes through `resume`.

The main workflow commands are:

- [`/flow-boot`](scaffolds/default/commands/flow-boot.md) — orient to project state, overlays, memory, and active work
- [`/flow-define`](scaffolds/default/commands/flow-define.md) — turn early feature or architectural-capability ideas into approved requirements
- [`/flow-solution`](scaffolds/default/commands/flow-solution.md) — choose a technical approach for approved requirements when options, architecture decisions, or chunking matter
- [`/flow-plan`](scaffolds/default/commands/flow-plan.md) — shape approved requirements or bug-shaped work into an implementation-ready plan
- [`/flow-implement`](scaffolds/default/commands/flow-implement.md) — run gated implementation with durable artifacts
- [`/flow-review`](scaffolds/default/commands/flow-review.md) — judge implementation against intent and validation evidence
- [`/flow-archive`](scaffolds/default/commands/flow-archive.md) — close accepted work and update durable memory
- [`/flow-scout`](scaffolds/default/commands/flow-scout.md) — handle small focused changes that meet the scout-size criteria
- [`/flow-resume`](scaffolds/default/commands/flow-resume.md) and [`/flow-status`](scaffolds/default/commands/flow-status.md) — recover or summarize current work state
- [`/flow-help`](scaffolds/default/commands/flow-help.md) and [`/flow-init-project`](scaffolds/default/commands/flow-init-project.md) — orient to Flow or initialize project-overlay context

### Framework content

The framework template includes:

- [command contracts](scaffolds/default/commands/) under `.flow/commands/`
- [agent role definitions](scaffolds/default/agents/) under `.flow/agents/`
- [standards](scaffolds/default/standards/) under `.flow/standards/`
- [templates](scaffolds/default/templates/) for definitions, research notes, adversarial reviews, ADRs, spikes, runs, and handoffs
- [project overlay starter files](scaffolds/default/project/) under `.flow/project/`
- [memory and run scaffolding](scaffolds/default/) for transient state and durable artifacts
- [flow.toml](scaffolds/default/flow.toml), the machine-readable manifest for commands, agents, hooks, model hints, and standard dependencies
- user overlays at `~/.flow/user/` for personal commands, agents, hooks, standards, or templates without forking this repo

A user overlay is your personal layer on top of the default framework. Put files in `~/.flow/user/` when you want an override or extension to follow you across projects.

User overlays are optional. Use `flow setup user --overlay-repo URL` if you want that overlay backed by your own git repo. Flow can clone an absent overlay or attach a remote to an existing one, but it does not clobber files or commit for you. For the merge model and ownership rules, see [architecture.md](docs/architecture.md).

### Want to install?

For a new machine, use [Quick Install](#quick-install-recommended-for-most-users).

For framework development, use [Local Install](#local-install-for-maintainers-and-contributors).

For a repo that needs project-specific memory, roles, or run artifacts, use [Typical Flow](#typical-flow).

### CLI Command Categories

Use the CLI by intent. Most day-to-day work happens through `/flow-*` workflow commands; shell commands install, sync, inspect, and maintain the framework.

#### Install and Update

Use these when setting up flow on a machine, connecting your user overlay to git, switching install modes, or updating a release install.

- `flow setup machine`
  - prepares `~/.flow/`, `~/.local/bin/flow`, and local config
- `flow setup user`
  - installs the framework at user level so it is active in every supported runtime session (runs `flow sync claude --user` and `flow sync codex --user`)
- `flow setup user --overlay-repo URL`
  - gives `~/.flow/user/` a git home at URL. It clones when the overlay is absent, or runs `git init` in place and adds the remote when content already exists. It never clobbers existing files and never commits.
- `flow install --release`
  - converts the local install to release mode by copying framework content into `~/.flow/source/`
- `flow install --develop PATH`
  - converts the local install to develop mode by pointing `~/.flow/source` at a checkout
- `flow update [--check] [--resync]`
  - rolls a release install forward to the latest tagged release; `--check` reports only, and `--resync` updates generated user-level adapters after the install

#### Project Setup

Use these when a repo needs a `.flow/` overlay for project-specific roles, memory, standards, or run artifacts.

- `flow setup project`
  - scaffolds `.flow/` into the current repo; use this only when you want a project overlay
- `flow refresh project`
  - adds newly introduced framework files into an existing `.flow/` without overwriting local edits
- `flow bootstrap`
  - validates that the required `.flow/` structure exists in the current repo

#### Runtime Sync

Use these after changing framework content, user overlays, project overlays, commands, agents, or hooks.

- `flow sync claude`
  - generates Claude adapters from the repo's `.flow/` into the repo's runtime locations
- `flow sync claude --user`
  - generates Claude adapters from the framework scaffold directly into user-level runtime locations
- `flow sync codex`
  - generates Codex adapters from the repo's `.flow/` into the repo's runtime locations
- `flow sync codex --user`
  - generates Codex adapters from the framework scaffold directly into user-level runtime locations
- `--check`
  - reports drift without writing files; use it with any sync target

Typical user-level sync:

```bash
flow sync claude --user
flow sync codex --user
flow sync claude --user --check
flow sync codex --user --check
```

#### Health Checks

Use these to inspect install state, generated runtime surfaces, drift, and command help.

- `flow doctor`
  - reports machine, user-level, and project-level state in separate sections
- `flow help`
  - renders the framework overview at the shell

#### Usage Store Maintenance

Most usage capture happens through Flow commands and hooks. Use these commands when you need to backfill, refresh historical data, or make summary views current before reading them.

Normal path:

- `flow cost active`
  - harvests Claude sessions and normalizes before it answers
- `flow cost verdict --hook`
  - is called by runtime Stop hooks and harvests the current transcript
- `flow cost warn --hook`
  - reads the verdict file; it does not harvest at prompt time

Manual maintenance:

- `flow harvest claude`
  - refreshes Claude usage data when you want `flow cost summary` or `flow cost sessions` to include the latest completed sessions
- `flow harvest claude --rescan`
  - rewinds already-recorded Claude file watermarks and re-reads them from the start. Already-harvested sessions can then pick up corrected output token counts, compaction events, `session.title`, `cwd`, and title provenance. `--since` and `--session` narrow the scope; `--dry-run` rehearses it. Safe to run repeatedly because the output-token rule is highest-wins.
- `flow harvest codex`
  - sweeps Codex session files into the usage store; broader Codex history is not swept by `flow cost active`
- `flow normalize`
  - rebuilds the normalized layer after a manual harvest; only rows without a current-version normalized counterpart are recomputed

#### Usage Analysis

Use these to read cost, context growth, active sessions, and token trends.

- `flow cost summary`
  - shows token totals by harness/model within a window (`--days N`, default 7; `--all` for everything), plus Codex's most recent capacity reading as a separate gauge line
- `flow cost sessions`
  - shows token totals by session within a window, most recently active first; capped at the 20 most recent by default (`--limit N` to change, `--limit 0` for unlimited)
- `flow cost trend`
  - shows efficiency per time bucket (`--bucket day|week`, `--harness claude|codex`): main-agent turns, sessions, context per turn, input:output, weighted tokens per 1,000 output, subagent share, and compaction events split by manual vs auto. Weighted columns are Claude-only and their multipliers live in `data/token_weights.json`.
- `flow cost active`
  - shows per-active-session context percentage, carry above session start, idle time, and a `/clear` or `/compact` recommendation, worst carry first. Runs incremental Claude harvest and normalize before answering (`--within N` minutes of liveness, default 60).
- `flow cost verdict`
  - gives live judgment for one session. This is the engine behind the Stop hooks on both runtimes: `--hook` reads the runtime's hook JSON on stdin and writes/removes `/tmp/<harness>-verdict-<session_id>` silently. The Claude statusline and warn hook read the file for free. `--transcript PATH` prints the judgment line for manual inspection.
- `flow cost warn`
  - powers the UserPromptSubmit pre-execution warning. It reads the verdict file without recomputing at prompt time, then prints one advisory line only when carry is heavy (100K+) and has grown 50K+ since the last warning. Informational only; always exits 0.
- `--json` on any `flow cost` view prints the same structured result as JSON instead of an aligned table

## What Gets Installed

At user level, flow installs the pieces each runtime needs:

- Claude gets `flow-*` skills, project subagents, and hooks that add flow context and warn when generated files are edited directly.
- Codex gets flow skills, native agent definitions, hooks, and a managed-file manifest.

## Why Generated Files Exist

Claude and Codex do not read the same configuration format. Flow keeps one source of truth under `.flow/`, then generates the shape each runtime expects.

That keeps commands, agents, and hooks portable without asking you to hand-maintain parallel Claude and Codex copies. For the full adapter model, see [runtime-adapters.md](docs/runtime-adapters.md).

### How Flow Reaches Claude and Codex

Flow keeps its source files under `.flow/`, then writes the runtime-specific files Claude and Codex need.

`flow sync claude` (project mode) writes into the repo's `.claude/`:

- `.claude/skills/<flow-command>/SKILL.md` from `.flow/commands/*.md`
- `.claude/agents/*.md` from `.flow/agents/*.md`
- `.claude/hooks/*.sh` from reusable hook scripts in this repo
- `.claude/settings.json` with managed hook configuration merged into existing settings
- `.claude/flow.managed.toml` machine-readable manifest of managed generated files

`flow sync claude --user` (user mode) generates the same surfaces into `~/.claude/`, with `$HOME`-based hook commands and manifest entries that reference the framework scaffold path. The session-start hook fires in every Claude Code session and detects project-level `.flow/` overlays automatically.

`flow sync codex` and `flow sync codex --user` do the same for Codex:

- `.agents/skills/<flow-command>/SKILL.md` from `.flow/commands/*.md` (or from the scaffold in user mode)
- `.codex/agents/*.toml` from `.flow/agents/*.md`, including model and reasoning-effort hints from `flow.toml`
- `.codex/hooks/*.sh` from `[[codex.hooks]]` entries (framework hooks or user-overlay hooks)
- `.codex/hooks.json` with managed hook handlers merged in under the same preserve-unmanaged contract as `.claude/settings.json` — `~/.codex/config.toml` is never touched
- `.codex/flow.managed.toml` machine-readable manifest of managed generated files

Codex hook support has parity with Claude's: same manifest shape (`name`/`event`/`matcher`/`type`/`script`, optional `timeout`/`status_message`), same overlay merge, same managed-entry lifecycle. `matcher` is optional for Codex; omitted means match everything, per Codex's own hook semantics.

## Files Flow Owns

These files are generated. Change the `.flow/` source files instead of editing the generated copies directly.

- `.claude/skills/...`
- `.claude/agents/...`
- `.claude/hooks/flow-*.sh`
- managed hook entries inside `.claude/settings.json`
- `.claude/flow.managed.toml`
- `.agents/skills/...`
- `.codex/agents/...`
- `.codex/hooks/flow-*.sh`
- managed hook entries inside `.codex/hooks.json`
- `.codex/flow.managed.toml`

Where to make changes:

- edit `.flow/commands/*` to change generated skills
- edit `.flow/agents/*` to change generated agents
- edit framework hook sources in this repo to change generated hook scripts
- rerun `flow sync claude` after changing the source of truth
- rerun `flow sync codex` after changing Codex-managed surfaces

Flow preserves unmanaged Claude and Codex files. It only removes files that were previously marked as flow-managed and are no longer part of the generated surface.

## Smoke-Tested Behavior

The current implementation has been smoke-tested for:

- `flow setup project`
- `flow bootstrap`
- `flow sync claude`
- `flow sync claude --check`
- generated skill and agent output
- generated hook scripts and executable bits
- managed settings generation
- generated Codex skill, agent, and hook output
- drift detection in `flow doctor`
- missing-file restoration in `flow refresh project`
- automated CLI tests for setup, sync, and drift behavior

## Quick Install (recommended for most users)

```bash
curl -fsSL https://raw.githubusercontent.com/andyconley/flow/main/install.sh | bash
flow setup machine
flow setup user
```

That command queries the flow remote for the latest tagged release, shallow-clones it to a temporary directory, installs the framework into `~/.flow/source/` in release mode, then cleans up. After it runs, the temp clone is disposable. The install is self-contained, and `flow update` rolls it forward to newer tagged releases later.

## Local Install (for maintainers and contributors)

To edit framework content yourself, clone the repo and use the maintainer flow:

```bash
git clone https://github.com/andyconley/flow.git ~/personal/flow
cd ~/personal/flow
./install-flow.sh                # develop mode (default) — symlink to this clone
flow setup machine
flow setup user                  # installs flow at user level — active in every supported runtime session
```

`./install-flow.sh` writes a `flow` launcher at `~/.local/bin/flow` and either symlinks (develop) or copies (release) the framework into `~/.flow/source`. `flow setup machine` creates the support directories under `~/.flow/`. `flow setup user` generates Claude surfaces under `~/.claude/`, Codex skills under `~/.agents/skills/`, and the Codex managed manifest under `~/.codex/`.

## Choosing an Install Mode

`install-flow.sh` supports two install modes. Both use the same path contract: `~/.flow/source/`.

| Mode | Storage | When to use |
|---|---|---|
| **Develop** (`--develop`, default) | `~/.flow/source` → symlink to this checkout | Maintainers and contributors editing framework content. Edits in the clone go live immediately. |
| **Release** (`--release`) | `~/.flow/source/` → real directory of copied content | Consumers who want flow installed without keeping a clone around. The clone is disposable after install. Use `flow update` to roll forward to newer tags. |

The mode and installed version are stamped into `~/.flow/config.toml` and reported by `flow doctor`.

### Develop install (current behavior)

```bash
cd ~/personal/flow
./install-flow.sh                # or: ./install-flow.sh --develop
flow setup machine
flow setup user
```

`~/.flow/source` is a symlink to your clone. Edits in the clone immediately change flow's behavior. Pull and resync to roll forward:

```bash
git -C ~/personal/flow pull --ff-only
flow sync claude --user
flow sync codex --user
```

### Release install

```bash
cd /tmp/flow-clone
git clone https://github.com/andyconley/flow.git .
./install-flow.sh --release
flow setup machine
flow setup user
cd / && rm -rf /tmp/flow-clone   # clone is disposable now
flow doctor                       # confirms release mode and installed version
```

`~/.flow/source/` is a real directory; the clone is no longer required. Roll forward to a newer tagged release:

```bash
flow update --check               # report current vs latest tag
flow update                       # apply: stage, atomic swap, update config
flow update --resync              # apply + re-run `flow sync claude --user` / `flow sync codex --user`
```

`flow update` stages the new content first, validates it, then atomically renames it into place. A failed update cannot leave a half-installed framework.

### Converting between modes

```bash
flow install --release                          # symlink → copied directory (clone preserved)
flow install --develop ~/personal/flow          # copied directory → symlink to clone
```

`flow doctor` reports the current install mode, version (release) or symlink target (develop), and how to check for updates.

## Typical Flow

**First-time install (once per machine):**

```bash
cd ~/personal/flow
./install-flow.sh
flow setup machine
flow setup user
```

**Optional: per-project overlay** (only for repos that need project-specific roles, durable memory, or run artifacts):

```bash
cd /path/to/project
flow setup project
flow bootstrap
flow sync claude
flow sync codex
flow doctor
```

**After framework changes** (when this repo updates):

```bash
flow sync claude --user
flow sync codex --user
```

## What’s Left

The framework is usable, but not finished. Main gaps:

- no content-aware upgrade path for existing project files beyond missing-file refresh
- no finer-grained managed-settings metadata beyond generated hook merging
- no project-specific migration helpers beyond the generic framework lifecycle

## Current Recommendation

`main` is the active branch. Both `main` and `develop` track the same content as of the most recent release; future work can branch from either, but `main` is what user-level installs reference.
