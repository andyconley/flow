# flow

Portable AI workflow framework.

## What It Is

`flow` operates across four layers:

1. **Machine support** at `~/.flow/` — install state, config, the source symlink
2. **Framework source** in this repo (`scaffolds/default/`) — the canonical workflow vocabulary
3. **User-level install** at `~/.claude/`, `~/.agents/skills/`, and `~/.codex/` — generated adapters active in every supported runtime session, regardless of cwd
4. **Project overlays** at `<repo>/.flow/` and their generated adapters at `<repo>/.claude/`, `<repo>/.agents/skills/`, and `<repo>/.codex/` — per-project, opt-in, only where you want project-specific role assignments / memory / run artifacts

Framework content (commands, agents, standards) is the source of truth; runtime-facing files in `.claude/`, `.agents/skills/`, and `.codex/` are generated adapters at both user-level and project-level scopes.

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
- vendored upstream specs (verbatim mirrors of external standards flow depends on) under `.flow/standards/vendor/` — e.g., the Conventional Commits v1.0.0 spec
- richer command contracts under `.flow/commands/`
- richer role definitions under `.flow/agents/`
- project overlay templates under `.flow/project/`
- memory, templates, and run scaffolding
- a machine-readable framework manifest at `.flow/flow.toml` (also declares dependencies on upstream standards via `[standards.<name>]` blocks)
- **user overlay support** at `~/.flow/user/` — drop your own commands, agents, hooks, standards, or templates here to override the framework defaults or add new ones, without forking. See `docs/architecture.md` "User Overlay" for the merge model.
- **overlay version control.** The overlay is the one authored layer with no home in any repo flow ships, so it starts with no history and no backup. `flow setup user --overlay-repo <url>` gives it one: clone when the overlay is absent (the new-machine path), or `git init` in place and add the remote when it already has content. It never clobbers existing files and never commits — `FRAMEWORK.md` holds the convention for who commits overlay edits. `flow doctor` reports the overlay's VCS state, uncommitted and unpushed work included.

### Workflow lanes

The default Flow lane is:

```text
boot -> define -> solution (optional) -> plan -> implement -> review -> archive
```

Small, narrow work can use `scout` directly. Interrupted work resumes through `resume`.

The main slash-command skills are:

- `/flow-boot` — orient to project state, overlays, memory, and active work
- `/flow-define` — turn early feature or architectural-capability ideas into approved requirements through discovery, research, adversarial review, and explicit approval
- `/flow-solution` — choose a technical approach for approved requirements when options, architecture decisions, or chunking matter
- `/flow-plan` — shape approved requirements or bug-shaped work into an implementation-ready plan
- `/flow-implement` — run gated implementation with durable artifacts
- `/flow-review` — judge implementation against intent and validation evidence
- `/flow-archive` — close accepted work and update durable memory
- `/flow-scout` — handle small focused changes that meet the scout-size criteria
- `/flow-resume` and `/flow-status` — recover or summarize current work state
- `/flow-help` and `/flow-init-project` — orient to Flow or initialize project overlay context

### Start here

For a new machine, use [Quick Install](#quick-install-recommended-for-consumers).

For framework development, use [Local Install](#local-install-for-maintainers-and-contributors).

For a repo that needs project-specific memory, roles, or run artifacts, use [Typical Flow](#typical-flow).

### CLI lifecycle

Available commands:

```bash
flow doctor
flow setup machine
flow setup user
flow setup user --overlay-repo git@github.com:you/flow-user-overlay.git
flow setup project
flow refresh project
flow bootstrap
flow sync claude              # project-level
flow sync claude --check
flow sync claude --user       # user-level
flow sync codex
flow sync codex --check
flow sync codex --user
flow harvest codex
flow harvest claude
flow harvest claude --rescan
flow harvest claude --rescan --since 2026-08-01 --dry-run
flow normalize
flow cost summary
flow cost summary --all --json
flow cost sessions --days 30
flow cost trend --days 30 --bucket week
flow cost sessions --all --limit 0
flow cost active
flow cost active --within 180
flow cost verdict --transcript PATH
```

What they do:

- `flow setup machine`
  - prepares `~/.flow/`, `~/.local/bin/flow`, and local config
- `flow setup user`
  - installs the framework at user level so it is active in every Claude session (runs `flow sync claude --user` and `flow sync codex --user`)
- `flow setup user --overlay-repo URL`
  - additionally gives `~/.flow/user/` a git home at URL: clones when the overlay is absent, or `git init`s in place and adds the remote when it already has content. Never clobbers existing files, never commits.
- `flow setup project`
  - scaffolds `.flow/` into the current repo (only needed when you want a project overlay)
- `flow refresh project`
  - adds newly introduced framework files into an existing `.flow/` without overwriting local edits
- `flow bootstrap`
  - validates that the required `.flow/` structure exists in the current repo
- `flow doctor`
  - reports machine, user-level, and project-level state in distinct sections
- `flow sync claude` / `flow sync codex`
  - generate adapters from the repo's `.flow/` into the repo's runtime locations
- `flow sync claude --user` / `flow sync codex --user`
  - generate adapters from the framework scaffold directly into the user-level runtime locations
- `--check` on any sync target reports drift without writing files
- `flow harvest codex` / `flow harvest claude`
  - incrementally read `~/.codex/sessions/` / `~/.claude/projects/` into `~/.flow/usage.db`'s raw layer (creating the store on first run); safe to run repeatedly or on a schedule
- `flow harvest claude --rescan`
  - rewinds already-recorded Claude files' watermarks and re-reads them from the start, so already-harvested sessions pick up corrected output token counts, compaction events, `session.title`, `cwd`, and title provenance retroactively; `--since` / `--session` narrow the scope and `--dry-run` rehearses it; safe to run repeatedly (the output-token rule is highest-wins, so a rescan cannot un-correct a row)
- `flow normalize`
  - projects every harness's raw turn records into one shared token convention (`turn_norm`); only rows without a current-version normalized counterpart are recomputed
- `flow cost summary`
  - token totals by harness/model within a window (`--days N`, default 7; `--all` for everything), plus Codex's most recent capacity reading as a separate gauge line
- `flow cost sessions`
  - token totals by session within a window, most recently active first; capped at the 20 most recent by default (`--limit N` to change, `--limit 0` for unlimited)
- `flow cost trend`
  - efficiency per time bucket (`--bucket day|week`, `--harness claude|codex`): main-agent turns, sessions, context per turn, input:output, weighted tokens per 1,000 output, subagent share, and compaction events split by manual vs auto. Weighted columns are Claude-only and their multipliers live in `data/token_weights.json`
- `flow cost active`
  - per-active-session context percentage, carry above session start, idle, and a `/clear`-or-`/compact` recommendation, worst carry first; runs the incremental Claude harvest and a normalize pass before answering (`--within N` minutes of liveness, default 60)
- `flow cost verdict`
  - live judgment for one session, the engine behind the Stop hooks on both runtimes: `--hook` reads the runtime's hook JSON on stdin and writes/removes `/tmp/<harness>-verdict-<session_id>` silently (the Claude statusline and the warn hook read the file for free); `--transcript PATH` prints the judgment line for manual inspection
- `flow cost warn`
  - the pre-execution warning behind the UserPromptSubmit hooks: reads the verdict file (no computation at prompt time) and prints one advisory line only when carry is heavy (100K+) and has grown 50K+ since the last warning; informational only, always exits 0
- `--json` on any `flow cost` view prints the same structured result as JSON instead of an aligned table

### Runtime adapter generation

`flow sync claude` (project mode) generates into the repo's `.claude/`:

- `.claude/skills/<flow-command>/SKILL.md` from `.flow/commands/*.md`
- `.claude/agents/*.md` from `.flow/agents/*.md`
- `.claude/hooks/*.sh` from reusable hook scripts in this repo
- `.claude/settings.json` with managed hook configuration merged into existing settings
- `.claude/flow.managed.toml` machine-readable manifest of managed generated files

`flow sync claude --user` (user mode) generates the same surfaces into `~/.claude/` instead, with `$HOME`-based hook commands and manifest entries that reference the framework scaffold path. The session-start hook then fires in every Claude Code session and detects project-level `.flow/` overlays automatically.

`flow sync codex` and `flow sync codex --user` follow the same pattern for Codex-native surfaces:

- `.agents/skills/<flow-command>/SKILL.md` from `.flow/commands/*.md` (or from the scaffold in user mode)
- `.codex/agents/*.toml` from `.flow/agents/*.md`, including model and reasoning-effort hints from `flow.toml`
- `.codex/hooks/*.sh` from `[[codex.hooks]]` entries (framework hooks or user-overlay hooks)
- `.codex/hooks.json` with managed hook handlers merged in under the same preserve-unmanaged contract as `.claude/settings.json` — `~/.codex/config.toml` is never touched
- `.codex/flow.managed.toml` machine-readable manifest of managed generated files

Codex hook support has full parity with Claude's: same manifest shape (`name`/`event`/`matcher`/`type`/`script`, optional `timeout`/`status_message`), same overlay merge, same managed-entry lifecycle. `matcher` is optional for Codex (omitted = match everything, per Codex's own hook semantics).

## Managed Boundaries

`flow` treats these as generated, managed surfaces:

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

Rules:

- edit `.flow/commands/*` to change generated skills
- edit `.flow/agents/*` to change generated agents
- edit framework hook sources in this repo to change generated hook scripts
- rerun `flow sync claude` after changing the source of truth
- rerun `flow sync codex` after changing Codex-managed surfaces

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
- agents are declared once and adapted per runtime
  - Claude receives agent Markdown with `model` and `effort`
  - Codex receives native TOML agents with `model`, `model_reasoning_effort`, and generated developer instructions
- hooks are registered through each runtime's managed configuration surface

The practical result is:

- Claude gets the richer full adapter surface
- Codex gets native skills, agents, hooks, and managed manifests
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
- generated Codex skill, agent, and hook output
- drift detection in `flow doctor`
- missing-file restoration in `flow refresh project`
- automated CLI tests for setup, sync, and drift behavior

## Quick Install (recommended for consumers)

```bash
curl -fsSL https://raw.githubusercontent.com/andyconley/flow/main/install.sh | bash
flow setup machine
flow setup user
```

That single command queries the flow remote for the latest tagged release, shallow-clones it to a temporary directory, installs the framework into `~/.flow/source/` in release mode, then cleans up. After it runs, you can throw the temp clone away — the install is self-contained, and `flow update` rolls it forward to newer tagged releases later.

## Local Install (for maintainers and contributors)

If you want to edit framework content yourself, clone the repo and use the maintainer flow:

```bash
git clone https://github.com/andyconley/flow.git ~/personal/flow
cd ~/personal/flow
./install-flow.sh                # develop mode (default) — symlink to this clone
flow setup machine
flow setup user                  # installs flow at user level — active in every Claude session
```

`./install-flow.sh` writes a `flow` launcher at `~/.local/bin/flow` and either symlinks (develop) or copies (release) the framework into `~/.flow/source`. `flow setup machine` creates the support directories under `~/.flow/`. `flow setup user` generates Claude surfaces under `~/.claude/`, Codex skills under `~/.agents/skills/`, and the Codex managed manifest under `~/.codex/` so they are available everywhere.

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
- no project-specific migration helpers beyond the generic framework lifecycle

## Current Recommendation

`main` is the active branch. Both `main` and `develop` track the same content as of the most recent release; future work can branch from either, but `main` is what user-level installs reference.
