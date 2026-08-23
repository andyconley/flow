# flow

Portable workflow framework for AI-assisted development.

## What It Is

`flow` is a local workflow layer for Claude and Codex. It installs shared commands, agent roles, standards, hooks, and templates so AI-assisted work follows a repeatable path instead of living only in chat.

Flow helps you move work through definition, solutioning, planning, implementation, review, and archive. It also tracks session size and token usage so it can warn when a session is getting heavy and should be compacted or cleared.

Flow keeps its data local. Usage records, session-derived metadata, project overlays, and generated runtime files stay on your machine unless you choose to commit, push, or share them yourself.

Use it when you want to:

- turn an early idea into approved requirements
- choose an approach before implementation starts
- keep implementation work gated and reviewable
- give agents consistent role expectations across projects
- leave behind useful state, requirements, notes, and handoffs

Flow is extensible. You can add your own commands, agents, hooks, standards, templates, and project notes without forking the framework. User overlays apply across your machine; project overlays apply only inside the repo that owns them.

Flow is not the project itself. It is the operating model around the project.

For the internal architecture, see [architecture.md](docs/architecture.md).

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

Start with commands and agents. The other files support customization, project overlays, and repeatable delivery.

Main surfaces:

- [command contracts](scaffolds/default/commands/) under `.flow/commands/`
- [agent role definitions](scaffolds/default/agents/) under `.flow/agents/`
- [standards](scaffolds/default/standards/), resolved at runtime from the user overlay or the framework default

Customization and project files:

- [templates](scaffolds/default/templates/) for definitions, research notes, adversarial reviews, ADRs, spikes, runs, runbooks, and handoffs
- [memory and run scaffolding](scaffolds/default/) for transient state and durable artifacts
- [flow.toml](scaffolds/default/flow.toml), the machine-readable manifest for commands, agents, hooks, model hints, and standard dependencies
- user overlays at `~/.flow/user/` for personal commands, agents, hooks, standards, or templates without forking this repo

A user overlay is your personal layer on top of the default framework. Put files in `~/.flow/user/` when you want an override or extension to follow you across projects.

A project overlay is the repo-local `.flow/` layer. It holds the project's own work — its context, its transient state, and its run artifacts. Commands, agents, standards, and templates are not copied into it; those come from the user-level install.

User overlays are optional. Use `flow setup user --overlay-repo URL` if you want that overlay backed by your own git repo. Flow can clone an absent overlay or attach a remote to an existing one, but it does not clobber files or commit for you. For the merge model and ownership rules, see [architecture.md](docs/architecture.md).

### Want to install?

For a new machine, use [First Install](#first-install-recommended-for-most-users).

For framework development, use [Maintainer Install](#maintainer-install).

For a repo that needs project-specific memory, roles, or run artifacts, use [After Install](#after-install).

## First Install (recommended for most users)

```bash
curl -fsSL https://raw.githubusercontent.com/andyconley/flow/main/install.sh | bash
flow setup machine
flow setup user
```

That command queries the flow remote for the latest tagged release, shallow-clones it to a temporary directory, installs the framework into `~/.flow/source/` in release mode, then cleans up. After it runs, the temp clone is disposable. The install is self-contained, and `flow update` rolls it forward to newer tagged releases later.

## Maintainer Install

To edit framework content yourself, clone the repo and use the maintainer flow:

```bash
git clone https://github.com/andyconley/flow.git ~/personal/flow
cd ~/personal/flow
./install-flow.sh                # develop mode (default) — symlink to this clone
flow setup machine
flow setup user                  # installs flow at user level — active in every supported runtime session
```

`./install-flow.sh` writes a `flow` launcher at `~/.local/bin/flow` and either symlinks (develop) or copies (release) the framework into `~/.flow/source`. `flow setup machine` creates the support directories under `~/.flow/`. `flow setup user` generates Claude surfaces under `~/.claude/`, shared Codex skills under `~/.agents/skills/`, and Codex agents, hooks, and managed manifests under `~/.codex/`.

## Install Modes

`install-flow.sh` supports two install modes. Both use the same path contract: `~/.flow/source/`.

| Mode | Storage | When to use |
|---|---|---|
| **Develop** (`--develop`, default) | `~/.flow/source` → symlink to this checkout | Maintainers and contributors editing framework content. Edits in the clone go live immediately. |
| **Release** (`install.sh`, or `install-flow.sh --release` from a clone) | `~/.flow/source/` → real directory of copied content | Most users who want flow installed without keeping a clone around. The clone is disposable after install. Use `flow update` to roll forward to newer tags. |

The mode and installed version are stamped into `~/.flow/config.toml` and reported by `flow doctor`.

### Develop Mode

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

### Release Mode From A Clone

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

### Mode Conversion

```bash
flow install --release                          # symlink → copied directory (clone preserved)
flow install --develop ~/personal/flow          # copied directory → symlink to clone
```

`flow doctor` reports the current install mode, version (release) or symlink target (develop), and how to check for updates.

## After Install

**Check the install:**

```bash
flow doctor
```

**Optional: per-project overlay** (only for repos that need project-specific roles, durable memory, or run artifacts):

```bash
cd /path/to/project
flow setup project
flow bootstrap
flow project audit
flow doctor
```

**After framework changes or overlay edits:**

```bash
flow sync claude --user
flow sync codex --user
```

## CLI Command Categories

Use the CLI by intent. Most day-to-day work happens through `/flow-*` workflow commands; shell commands install, sync, inspect, and maintain the framework.

This is the command map, not the full reference. For detailed flags and behavior, see [cli-reference.md](docs/cli-reference.md).

### Install and Update

Most users only need the bootstrap installer once, then `flow update --resync` later. Use the other commands when setting up a machine, connecting your user overlay to git, or converting an existing install between modes.

- `flow setup machine`
  - prepare `~/.flow/`, `~/.local/bin/flow`, and local config
- `flow setup user`
  - install the framework at user level so it is active in every supported runtime session
- `flow setup user --overlay-repo URL`
  - give `~/.flow/user/` a git home without clobbering files or committing for you
- `flow install --release`
  - convert an existing develop install to release mode
- `flow install --develop PATH`
  - convert an existing release install to develop mode
- `flow update [--check] [--resync]`
  - update a release install to the latest tagged release

### Project Setup

Use these when a repo needs a `.flow/` overlay for its own context, transient state, or run artifacts.

- `flow setup project`
  - scaffold `.flow/` into the current repo
- `flow refresh project`
  - retired. A project no longer holds framework files, so there is nothing to refresh from the scaffold. Missing core files are `flow setup project`'s job; framework copies still present are `flow project audit` and `flow project migrate`'s.
- `flow project audit`
  - classify what a repo's `.flow/` is still carrying, read-only
- `flow project migrate`
  - remove the framework copies audit finds; dry run unless `--apply --yes`
- `flow bootstrap`
  - validate that the required `.flow/` structure exists

### Runtime Sync

Use these after changing framework content, user overlays, project overlays, commands, agents, or hooks.

- `flow sync claude --user`
  - generate Claude runtime files at user level
- `flow sync codex --user`
  - generate Codex runtime files at user level
- `flow runtime smoke --target all`
  - check generated Claude/Codex surfaces and list manual runtime smoke evidence

`--user` is required. Project-level sync was retired: it existed to regenerate
adapters from a project's own copies of the framework's commands and agents,
and projects no longer hold copies. `flow project migrate` removes the adapters
an earlier project-level sync left behind.
- `--check`
  - report drift without writing files; use it with any sync target

Typical user-level sync:

```bash
flow sync claude --user
flow sync codex --user
flow sync claude --user --check
flow sync codex --user --check
flow runtime smoke --target all
```

### Health Checks

Use these to inspect install state, generated runtime surfaces, drift, and command help.

- `flow doctor`
  - report machine, user-level, and project-level state
- `flow run list`
  - list active C-lite runs and legacy/inferred run artifact folders
- `flow run status WORK_ID`
  - show one run's current state from `.flow/runs/<work-id>/run.json`
- `flow run verify WORK_ID`
  - check `run.json` against append-only `events.jsonl`
- `flow help`
  - render the framework overview at the shell

### Workflow Run State

Use these when a `/flow-*` command needs to record or inspect the hard-gated lifecycle state for one work item. `run.json` is the current-state projection; `events.jsonl` is the append-only history. `flow run transition` is the only lifecycle writer.

- `flow run transition WORK_ID EVENT`
  - apply a legal transition such as `start-definition`, `approve-plan`, `mark-handback-ready`, `accept-review`, or `archive`
- `--artifact NAME=PATH`
  - attach required gate evidence such as `requirements`, `plan`, `validation_plan`, `implementation_evidence`, or `review`
- `--disposition NAME=VALUE`
  - attach required closure decisions such as `capability_gaps=n/a` and `memory=updated`
- `flow run history WORK_ID`
  - read the transition history

### Usage Store Maintenance

Most usage capture happens through Flow commands and hooks. Use these commands when you need to backfill, refresh historical data, or make summary views current before reading them. The design is explained in [flow cost capture design](docs/specs/2026-08-15-flow-cost-capture-design.md).

Normal path:

- `flow cost active`
  - harvest Claude sessions and normalize before it answers
- `flow cost verdict --hook`
  - harvest the current transcript from runtime Stop hooks
- `flow cost warn --hook`
  - read the verdict file without harvesting at prompt time

Manual maintenance:

- `flow harvest claude`
  - refresh Claude usage data for summary views
- `flow harvest claude --rescan`
  - re-read already-harvested Claude transcripts after collector improvements or historical-data fixes
- `flow harvest codex`
  - sweep Codex session files into the usage store
- `flow normalize`
  - rebuild the normalized layer after a manual harvest

### Usage Analysis

Use these to read cost, context growth, active sessions, and token trends. For the capture model, normalization rules, and hook behavior, see [flow cost capture design](docs/specs/2026-08-15-flow-cost-capture-design.md).

- `flow cost summary`
  - show token totals by harness/model
- `flow cost sessions`
  - show token totals by session
- `flow cost trend`
  - show usage trends by day or week
- `flow cost active`
  - show active-session context percentage and compact/clear guidance
- `flow cost verdict`
  - judge one session for runtime hooks or manual inspection
- `flow cost warn`
  - print the pre-execution warning when carry is heavy
- `--json`
  - print structured output for any `flow cost` view

### Plugin And Skill Usage

`flow cost` answers what a session spent. These answer whether the configuration it loaded is being used at all, by sampling the usage counters the harness maintains in its own config and reporting movement over time. The design is explained in [plugin usage history design](docs/specs/2026-08-18-plugin-usage-history-design.md).

- `flow plugin-usage snapshot`
  - record the current counters if they have moved since the last look
- `flow plugin-usage show`
  - print the report `flow doctor` also renders as a section

**Claude only.** Codex maintains no equivalent counters, so on Codex the section states that rather than rendering an empty table. This is the same capability-gated asymmetry `flow cost baseline` carries for compaction filtering, declared in `data/harness_capabilities.json`.

Two things to know before acting on the numbers. **A high count usually means hooks, not use** — the harness increments a plugin's counter once per hook firing, so a plugin registering several hooks accumulates tens of thousands of firings without ever being invoked deliberately; those are reported in a separate block and never counted as invocations. And **history starts when flow starts looking** — the harness keeps none to backfill from, so the counts inherited at the first snapshot are archaeology, while the deltas between later snapshots are sound.

## How Flow Manages Runtime Files

Most users only need to know that flow writes the Claude and Codex files each runtime expects. For the full adapter model and file list, see [runtime-adapters.md](docs/runtime-adapters.md).

### What Gets Installed

At user level, flow installs the pieces each runtime needs:

- Claude gets `flow-*` skills, project subagents, and hooks that add flow context and warn when generated files are edited directly.
- Codex gets flow skills, native agent definitions, hooks, and a managed-file manifest.

### Why Generated Files Exist

Claude and Codex do not read the same configuration format. Flow keeps one source of truth under `.flow/`, then generates the shape each runtime expects.

That keeps commands, agents, and hooks portable without asking you to hand-maintain parallel Claude and Codex copies.

### Files Flow Owns

Flow-managed files are generated. Change the `.flow/` source files instead of editing generated copies directly:

- edit `.flow/commands/*` to change generated skills
- edit `.flow/agents/*` to change generated agents
- edit framework hook sources in this repo to change generated hook scripts
- rerun `flow sync claude --user` and `flow sync codex --user` after changing the source of truth

Flow preserves unmanaged Claude and Codex files. It only removes files that were previously marked as flow-managed and are no longer part of the generated surface.

## Maintainer Docs

For maintainer-oriented documentation, start with:

- [architecture.md](docs/architecture.md)
- [file-structure.md](docs/file-structure.md)
- [cli-reference.md](docs/cli-reference.md)
- [runtime-adapters.md](docs/runtime-adapters.md)
- [backlog.md](docs/backlog.md)

## Current Repo Layout

- `cli/` - local CLI entrypoint
- `docs/` - maintainer docs for architecture, file structure, runtime adapters, and backlog
- `scaffolds/default/` - the framework scaffold copied into user-level installs and per-project overlays
- `hooks/` - reusable Claude hook scripts bundled by `flow`
- `scripts/` - reserved for framework maintenance helpers
- `tests/` - CLI-level regression tests

## Validation

Current validation covers setup, sync, generated files, drift detection, refresh behavior, and CLI regression tests.

- `flow setup project`
- `flow bootstrap`
- `flow project audit`
- `flow sync claude --user`
- `flow sync claude --user --check`
- generated skill and agent output
- generated hook scripts and executable bits
- managed settings generation
- generated Codex skill, agent, and hook output
- drift detection in `flow doctor`
- overlay classification and migration in `flow project audit` / `flow project migrate`
- automated CLI tests for setup, sync, and drift behavior

## What’s Left

The framework is usable, but not finished. Main gaps:

- no content-aware upgrade path for existing project files beyond missing-file refresh
- no finer-grained managed-settings metadata beyond generated hook merging
- no project-specific migration helpers beyond the generic framework lifecycle

## Current Recommendation

`main` is the active development branch. Develop installs point `~/.flow/source` at a checkout; release installs follow tagged releases and can lag behind `main` until a new tag is cut.

Releases are automated from Conventional Commits on `main`. The release workflow updates `CHANGELOG.md`, tags the new version, and creates the GitHub release.

For a release-impacting documentation change, use a Conventional Commit type and scope that matches the behavior being described.

## License

Flow is released under the [MIT License](LICENSE).
