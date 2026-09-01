# Flow Framework

Portable workflow contract.

## Purpose

- define reusable workflow phases
- separate framework rules from project rules
- keep project memory and run artifacts durable

## Operating model

This framework has two distinct layers:

- **Framework** lives at the user level (installed into `~/.claude/`, `~/.agents/skills/`, and `~/.codex/`, sourced from this scaffold). Defines the workflow vocabulary (commands), the role agents, hooks, and the shared standards library. Active in every supported runtime session regardless of cwd.
- **Project overlays** live per-project in `<repo>/.flow/`. Hold that project's context, its transient work state, and its run artifacts — and nothing the framework already provides. Overlays stack — when working in a nested project, the workspace overlay (e.g., `~/KB/.flow/`) and the project overlay (e.g., `~/KB/repos/path-nexus/.flow/`) merge.

When stacked overlays merge, the more-specific overlay overrides on conflicts. Memory writes always go to the most-specific overlay; reads merge across all stacked levels. What stacks is context and state; commands, agents, standards, and templates do not, because a project holds none.

Each project overlay records, in `PROJECT.md`:

- role providers
- source-of-truth order
- runtime and integration constraints

## Default phases

The standard flow is:

1. boot
2. define
3. solution (optional)
4. plan
5. implement
6. review
7. archive or resume

Not every task needs every phase. Small work should stay small.

## Core commands

- `/flow-boot`
- `/flow-scout`
- `/flow-define`
- `/flow-solution`
- `/flow-plan`
- `/flow-implement`
- `/flow-review`
- `/flow-archive`
- `/flow-resume`
- `/flow-status`

## File model

A project overlay holds the project's own work and nothing else. Commands,
agents, standards, and templates come from the user-level install.

- `flow.toml` - the overlay's manifest
- `PROJECT.md` - project identity and context
- `memory/STATE.md` - transient work state (what is in flight, blocked, or pending right now)
- `runs/` - per-work-item artifacts
- `runs/<work-id>/run.json` - C-lite current-state projection for gated workflow runs
- `runs/<work-id>/events.jsonl` - append-only transition history for that run
- `runs/<work-id>/orchestration.json` - protocol-revision-2 orchestration contract

Durable project facts and cross-cutting decisions do NOT live in `.flow/memory/`.
They live in the active runtime's durable memory provider when one exists. For
Claude Code, that provider is auto-memory at
`~/.claude/projects/<project-id>/memory/`. Codex currently has no equivalent
Flow-managed durable memory provider, so project artifacts and C-lite run state
remain canonical there.

## Runtime context providers

Flow's shared commands are runtime-neutral. They treat project `.flow/`
artifacts as canonical and runtime memory as companion context:

- canonical project identity: `.flow/PROJECT.md`
- canonical transient work state: `.flow/memory/STATE.md`
- canonical run lifecycle: `.flow/runs/<work-id>/run.json` and `events.jsonl`
- canonical revision-2 orchestration contract: `.flow/runs/<work-id>/orchestration.json`
- durable memory provider, when available: runtime-specific companion memory

When a command mentions durable runtime memory, resolve it through the active
provider. Claude Code uses `~/.claude/projects/<project-id>/memory/`. Codex has
no Flow-managed durable memory provider yet; do not invent one, and do not
treat missing Codex memory as missing workflow state.

## Canonical sources

This framework prefers durable files over chat. When stacked overlays exist, more-specific overlays win on conflicts.

By default, use:

1. issue tracker or explicitly assigned work item
2. `.flow/PROJECT.md` (read from every stacked overlay level)
3. relevant standards and templates, resolved as below
4. ADRs and code
5. `.flow/memory/STATE.md` (transient work state — read from every stacked overlay level)
6. the active runtime memory provider, when one exists (durable project facts and decisions; for Claude Code, consult `~/.claude/projects/<project-id>/memory/MEMORY.md` as the index)

## Overlay resolution for standards and templates

Commands and agents cite standards by name (e.g., `standards/git-commits.md`) and may cite templates similarly (e.g., `templates/spike-template.md`). At runtime, look for these files in **most-specific-wins** order:

1. **Project wiring** — if `.flow/flow.toml` declares a `[[replaces]]` entry whose `default` matches the name being cited, read its `with` instead, resolved under `~/.flow/user/`, and do **not** also read the default. Only `standards/` and `templates/` names are wirable. When overlays stack, the nearest `.flow/flow.toml` wins on a matching `default`; `flow doctor` checks only that level. **If the `with` file is not present, fall back to rule 2 and then rule 3, and say which you used in the role's output** — a wiring is a per-user promise the repo cannot keep for a teammate, so a missing replacement is the ordinary case on anyone else's machine, not an error. `flow doctor` reports each wiring as `ok`, `absent` (nothing at that path on this machine), or `unknown` (nothing resolves the cited name at all).
2. **User overlay** — `~/.flow/user/standards/<name>.md` or `~/.flow/user/templates/<name>.md`. Personal customizations that apply in every session.
3. **Framework default** — `~/.flow/source/scaffolds/default/standards/<name>.md` or `~/.flow/source/scaffolds/default/templates/<name>.md`. The shipped baseline.

Projects do not hold standards or templates. They used to, and the copies went stale without anyone noticing, because nothing updated them and the difference from the framework's version was invisible from inside the project. A project that needs a different standard puts it in the user overlay, where one copy serves every repo, and names it with a `[[replaces]]` entry as above — the project points at the file, it does not hold it. `flow project audit` reports any project still carrying its own copies.

Use the Read tool to resolve. If a name is cited and the user overlay has its own version, use that and note the resolution in the role's output if the difference matters. Commands, agents, and hooks are merged at sync time (see `merge_user_overlay` in `cli/sync.py`); standards and templates are resolved at runtime by this convention.

### Committing user-overlay edits

`~/.flow/user/` may be a git repo — `flow setup user --overlay-repo <url>` attaches one, and `flow doctor` reports whether it has history. When it does, **the agent that edits overlay content commits it in the same turn**: a personal command body, an agent override, a hook script, or the `flow.toml` registration. The person who owns that content is not the one typing in the directory, so waiting for them to notice pending changes leaves authored work uncommitted until something breaks. Push in the same turn too when the branch has an upstream — `doctor` reports `N unpushed`, so committing without pushing produces exactly the state it flags.

Two hooks watch for sessions that drift from this: one fires just after a write to versioned content, the other at the next prompt boundary while work is still outstanding. Both print a single advisory line and neither blocks anything — they exist because a convention that lives only in a document does not survive a compaction. `flow overlay status` answers the same question on demand, and `flow doctor`'s `vcs:` line under `user overlay:` remains the backstop for anything edited outside that path.

The overlay may sit inside a larger repository — a dotfiles home, say — rather than being one itself. When it does, these reports describe that whole repository, which is the intended reading: uncommitted work beside the overlay is the same hazard as uncommitted work in it.

## Role provider model

The same workflow role may be provided by:

- a human
- the main coding agent
- a subagent
- another external agent

Projects should declare who provides shaping, implementation, and acceptance review.

## Standard categories

The framework standards directory is expected to hold reusable operating guidance for areas such as:

- collaboration
- definition and research evidence
- architecture
- patterns
- testing
- observability
- delivery
- security
- supply chain
- documentation
- API governance
- event-driven systems
- developer experience
- team design
- data engineering
- AI/ML
- incident management
- FinOps
- accessibility and i18n
- open-source governance
- sustainability
- reference stack guidance
