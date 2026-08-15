# Flow Framework

Portable workflow contract.

## Purpose

- define reusable workflow phases
- separate framework rules from project rules
- keep project memory and run artifacts durable

## Operating model

This framework has two distinct layers:

- **Framework** lives at the user level (installed into `~/.claude/`, sourced from this scaffold). Defines the workflow vocabulary (commands), the role agents, and the shared standards library. Active in every Claude session regardless of cwd.
- **Project overlays** live per-project in `<repo>/.flow/`. Hold project-specific role assignments, sources of truth, durable memory, and run artifacts. Overlays stack — when working in a nested project, the workspace overlay (e.g., `~/KB/.flow/`) and the project overlay (e.g., `~/KB/repos/path-nexus/.flow/`) merge.

When stacked overlays merge, the more-specific overlay overrides on conflicts. Memory writes always go to the most-specific overlay; reads merge across all stacked levels.

Each project overlay defines:

- role providers
- active standards (subset of the framework's standards library that applies here)
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

- `PROJECT.md` - project overlay
- `standards/` - reusable standards categories
- `project/` - project-specific content
- `memory/STATE.md` - transient work state (what is in flight, blocked, or pending right now)
- `runs/` - per-work-item artifacts

Durable project facts and cross-cutting decisions do NOT live in `.flow/memory/` — they live in Claude Code's auto-memory at `~/.claude/projects/<project-id>/memory/`. `flow-archive` writes there explicitly.

## Canonical sources

This framework prefers durable files over chat. When stacked overlays exist, more-specific overlays win on conflicts.

By default, use:

1. issue tracker or explicitly assigned work item
2. `.flow/PROJECT.md` (read from every stacked overlay level)
3. relevant files in `.flow/standards/` and `.flow/project/`
4. ADRs and code
5. `.flow/memory/STATE.md` (transient work state — read from every stacked overlay level)
6. Claude Code auto-memory at `~/.claude/projects/<project-id>/memory/` (durable project facts and decisions; consult `MEMORY.md` as the index)

## Overlay resolution for standards and templates

Commands and agents cite standards by name (e.g., `standards/git-commits.md`) and may cite templates similarly (e.g., `templates/spike-template.md`). At runtime, look for these files in **most-specific-wins** order:

1. **Project overlay** — `<repo>/.flow/standards/<name>.md` or `<repo>/.flow/templates/<name>.md`. Only when invoked inside a repo with a `.flow/` overlay; the most-specific overlay walked up from the current directory wins.
2. **User overlay** — `~/.flow/user/standards/<name>.md` or `~/.flow/user/templates/<name>.md`. Personal customizations that apply in every session.
3. **Framework default** — `~/.flow/source/scaffolds/default/standards/<name>.md` or `~/.flow/source/scaffolds/default/templates/<name>.md`. The shipped baseline.

Use the Read tool to resolve. If a name is cited and the project overlay or user overlay has its own version, use that and note the resolution in the role's output if the difference matters. Commands, agents, and hooks are merged at sync time (see `merge_user_overlay` in `cli/sync.py`); standards and templates are resolved at runtime by this convention.

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
