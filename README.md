# flow

Portable AI workflow framework.

## What It Is

`flow` operates across four layers:

1. **Machine support** at `~/.flow/` — install state, config, the source symlink
2. **Framework source** in this repo (`scaffolds/default/`) — the canonical workflow vocabulary
3. **User-level install** at `~/.claude/` and `~/.codex/` — generated adapters active in **every** Claude session, regardless of cwd
4. **Project overlays** at `<repo>/.flow/` and their generated adapters at `<repo>/.claude/` and `<repo>/.codex/` — per-project, opt-in, only where you want project-specific role assignments / memory / run artifacts

Framework content (commands, agents, standards) is the source of truth; runtime-facing files in `.claude/` and `.codex/` are generated adapters at both user-level and project-level scopes.

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
flow setup user
flow setup project
flow refresh project
flow bootstrap
flow sync claude              # project-level
flow sync claude --check
flow sync claude --user       # user-level
flow sync codex
flow sync codex --check
flow sync codex --user
```

What they do:

- `flow setup machine`
  - prepares `~/.flow/`, `~/.local/bin/flow`, and local config
- `flow setup user`
  - installs the framework at user level so it is active in every Claude session (runs `flow sync claude --user` and `flow sync codex --user`)
- `flow setup project`
  - scaffolds `.flow/` into the current repo (only needed when you want a project overlay)
- `flow refresh project`
  - adds newly introduced framework files into an existing `.flow/` without overwriting local edits
- `flow bootstrap`
  - validates that the required `.flow/` structure exists in the current repo
- `flow doctor`
  - reports machine, user-level, and project-level state in distinct sections
- `flow sync claude` / `flow sync codex`
  - generate adapters from the repo's `.flow/` into the repo's `.claude/` or `.codex/`
- `flow sync claude --user` / `flow sync codex --user`
  - generate adapters from the framework scaffold directly into `~/.claude/` or `~/.codex/`
- `--check` on any sync target reports drift without writing files

### Runtime adapter generation

`flow sync claude` (project mode) generates into the repo's `.claude/`:

- `.claude/skills/<flow-command>/SKILL.md` from `.flow/commands/*.md`
- `.claude/agents/*.md` from `.flow/agents/*.md`
- `.claude/hooks/*.sh` from reusable hook scripts in this repo
- `.claude/settings.json` with managed hook configuration merged into existing settings
- `.claude/flow.managed.toml` machine-readable manifest of managed generated files

`flow sync claude --user` (user mode) generates the same surfaces into `~/.claude/` instead, with `$HOME`-based hook commands and manifest entries that reference the framework scaffold path. The session-start hook then fires in every Claude Code session and detects project-level `.flow/` overlays automatically.

`flow sync codex` and `flow sync codex --user` follow the same pattern but generate a narrower surface:

- `.codex/skills/<flow-command>/SKILL.md` from `.flow/commands/*.md` (or from the scaffold in user mode)
- `.codex/flow.managed.toml` machine-readable manifest of managed generated files

The Codex target is intentionally narrower than Claude — it proves `flow` is not Claude-only while only generating surfaces that map cleanly to the current Codex runtime model.

## Managed Boundaries

`flow` treats these as generated, managed surfaces:

- `.claude/skills/...`
- `.claude/agents/...`
- `.claude/hooks/flow-*.sh`
- managed hook entries inside `.claude/settings.json`
- `.claude/flow.managed.toml`
- `.codex/skills/...`
- `.codex/flow.managed.toml`

Rules:

- edit `.flow/commands/*` to change generated skills
- edit `.flow/agents/*` to change generated agents
- edit framework hook sources in this repo to change generated hook scripts
- rerun `flow sync claude` after changing the source of truth
- rerun `flow sync codex` after changing Codex-managed command surfaces

`flow sync claude` preserves unmanaged Claude files and only removes files that were previously marked as flow-managed and are no longer desired.
`flow sync codex` follows the same managed-manifest pattern for Codex skills.

## Claude Runtime Behavior

The generated Claude runtime currently includes:

- slash-command style skills for `flow-*`
- project subagents from `.flow/agents`
- a `SessionStart` hook that injects flow orientation context
- a `PostToolUse` reminder hook that nudges edits back to `.flow/` when generated Claude files are modified directly

## Adapter Decisions

The current adapter strategy is intentional:

- commands are adapter-generated per runtime
  - `.flow/commands/*.md` are generic workflow contracts, so each runtime can wrap them differently
- agents currently sync as near-verbatim copies for Claude
  - the source agent files are already close to Claude's usable shape
  - keeping them direct avoids duplicate bodies and reduces drift risk
- Codex currently gets command skills only
  - skills map cleanly to the Codex runtime
  - hooks, settings, and agent generation are not emitted there yet because that runtime contract is not as clearly defined

The practical result is:

- Claude gets the richer full adapter surface
- Codex gets a narrower but real skill surface
- the source of truth stays in `.flow/`, not in runtime-specific folders

## Smoke-Tested Behavior

The current implementation has been smoke-tested for:

- `flow setup project`
- `flow bootstrap`
- `flow sync claude`
- `flow sync claude --check`
- generated skill and agent output
- generated hook scripts and executable bits
- managed settings generation
- generated Codex skill output
- drift detection in `flow doctor`
- missing-file restoration in `flow refresh project`
- automated CLI tests for setup, sync, and drift behavior

## Local Install

```bash
./install-flow.sh                # develop mode (default) — symlink to this clone
flow setup machine
flow setup user                  # installs flow at user level — active in every Claude session
```

`./install-flow.sh` writes a `flow` launcher at `~/.local/bin/flow` and either symlinks (develop) or copies (release) the framework into `~/.flow/source`. `flow setup machine` creates the support directories under `~/.flow/`. `flow setup user` generates the framework's commands, agents, and hooks into `~/.claude/` and `~/.codex/` so they are available everywhere.

## Choosing an Install Mode

`install-flow.sh` supports two install modes that share the same path contract (`~/.flow/source/`):

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

`~/.flow/source` is a symlink to your clone. Editing files in the clone immediately changes flow's behavior. Pull-and-resync to roll forward:

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

`flow update` stages the new content first, validates it, then atomically renames it into place — a failed update can never leave a half-installed framework.

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

**Optional: per-project overlay** (only for repos that need project-specific role assignments, durable memory, or run artifacts):

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

The framework is now usable, but it is not finished. Main gaps:

- no content-aware upgrade path for existing project files beyond missing-file refresh
- no finer-grained managed-settings metadata beyond generated hook merging
- no richer non-Claude runtime surface yet beyond Codex skill generation
- no runtime-specific agent adapter layer beyond Claude verbatim sync
- no project-specific migration helpers beyond the generic framework lifecycle

## Current Recommendation

`main` is the active branch. Both `main` and `develop` track the same content as of the most recent release; future work can branch from either, but `main` is what user-level installs reference.
