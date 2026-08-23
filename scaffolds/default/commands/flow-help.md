# flow-help

Show the flow framework overview: phase machine, command catalog, agent roster, and architecture summary.

## Overview

This command is the framework's discoverable entry point. Use it to answer "what does flow do?" and "which command or agent fits this task?" without re-reading every command contract.

## When to Use

Use this command when:

- you want to remember which command does what
- you're new to flow and want orientation
- you want to look up an agent role without re-reading the framework docs
- you want to show a collaborator how the framework is shaped

**When NOT to use:** to learn the full workflow inside a specific command. Those phases live in each command's own contract. `flow-help` is the orientation surface.

## Primary inputs

- the framework's own identity (this file + FRAMEWORK.md)
- no project state required; `flow-help` is intentionally project-agnostic

## Primary outputs

- a one-screen orientation including phase machine, command catalog, agent roster, architecture summary, and pointers to deeper docs

## Help Workflow

1. State the framework's one-line identity.
2. Render the phase machine diagram.
3. List the available commands with one-line "use when" guidance.
4. List the available agents with one-line role descriptions and the core+conditional invocation pattern.
5. Summarize architecture (user-level vs project-level; runtime memory provider vs STATE.md vs runs).
6. List common entry points by intent ("Start a fresh session" → /flow-boot, etc.).
7. Point at deeper docs (`FRAMEWORK.md`, the maintainer docs at `~/.flow/source/docs/`).

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

```md
## flow Framework

Personal AI workflow framework. It defines HOW Claude and Codex operate with you, not WHAT you work on. Active in every supported runtime session through the user-level install.

## Phase machine

boot ──┬─→ scout (XS/S, narrow) ────────────────────────────→ archive
       │                                                      ↑
       └─→ define ──→ [solution] ──→ plan ──→ implement (gated) ──→ review ┘
                                                     ↑
                                                     └── resume (recover from interruption)

`define` turns early feature or architectural-capability ideas into approved requirements. `[solution]` is an optional pre-plan step after definition; use it when multiple approaches exist, architectural decisions are needed, or the work needs chunking before `plan` can shape it. Bug-shaped work can go directly to `/flow-plan`.

## Command surfaces

Flow has **two distinct command surfaces** — invoke each differently:

### Workflow commands

These are the commands you use during work. Claude exposes them as slash commands (`/flow-XXX`). Codex receives the same command bodies as skills.

<!-- generated:slash-commands-table:begin (regenerate with `scripts/regenerate-flow-help.py`) -->
| Command | Use when |
|---|---|
| /flow-boot | Starting a session, resuming, or context feels stale |
| /flow-scout | XS/S changes — single primary file, no new abstractions, validates in <5min |
| /flow-define | Early ideas or capabilities → approved requirements for plan or solution |
| /flow-solution | Optional pre-plan step when multiple approaches exist or architectural decisions are needed |
| /flow-plan | Idea / bug / request → implementation-ready plan |
| /flow-implement | Gated multi-phase work; runs land under `.flow/runs/<work-id>/` |
| /flow-review | Structured review after implementation |
| /flow-archive | Close a run; STATE.md → transient state; durable decisions → runtime memory provider |
| /flow-resume | Pick up interrupted work |
| /flow-status | Where are we, what's next? |
| /flow-init-project | Walk through filling in `.flow/PROJECT.md` (right after `flow setup project`) |
| /flow-help | This help output |
<!-- generated:slash-commands-table:end -->

The table above is derived from `[[claude.commands]]` `summary` fields in `flow.toml`; the Codex adapter uses matching `[[codex.commands]]` entries for its skill surface.

### CLI commands (run from the shell, or ask the active runtime to run them)

These are *lifecycle* commands: the things you do to install, sync, or check flow itself. Invoke them from a terminal as `flow XXX YYY`, or ask the active runtime to run them. They are NOT slash commands and won't work as `/flow XXX`.

<!-- generated:cli-commands-table:begin (regenerate with `scripts/regenerate-flow-help.py`) -->
| Command | Use when |
|---|---|
| `flow help` | This overview, but rendered at the shell (same content as `/flow-help`) |
| `flow setup machine` | First-time machine setup — creates `~/.flow/` support directories |
| `flow setup user` | Install flow at user level (active in every supported runtime session) |
| `flow setup project` | Scaffold `.flow/` overlay into the current repo |
| `flow sync claude [--user] [--check]` | Generate or check Claude adapters |
| `flow sync codex [--user] [--check]` | Generate or check Codex adapters |
| `flow install --release / flow install --develop <path>` | Convert the local install between modes (symlink ↔ copy) |
| `flow update [--check] [--resync]` | Roll a release install forward to the latest tagged release |
| `flow bootstrap` | Validate the current repo's `.flow/` structure |
| `flow doctor` | Report machine, install, user-level, and project-level state |
| `flow project audit` | Classify a repo's `.flow/` overlay against the framework (read-only) |
| `flow project migrate` | Remove the framework copies `audit` finds; dry run unless `--apply --yes` |
| `flow run list/status/history/verify/transition` | Inspect and hard-gate C-lite workflow run state |
| `flow runtime smoke [--target all|claude|codex] [--json]` | Check generated runtime surfaces and list manual runtime smoke evidence |
<!-- generated:cli-commands-table:end -->

The table above is derived from `[[help.cli_commands]]` in `flow.toml`.

## Agents

13 working agents. Light commands (boot, scout, resume, status, help) skip them. Heavier commands (define, solution, plan, implement, review, archive) use a **core trio + conditional specialists** pattern: core agents always engage, and conditional agents join when their concern applies.

<!-- generated:agents-table:begin (regenerate with `scripts/regenerate-flow-help.py`) -->
| Agent | Role |
|---|---|
| architect | Boundaries, integrations, ADR decisions |
| business-analyst | Problem framing, acceptance criteria |
| data-engineer | Persistent state changes, schema, migration |
| lead-developer | Execution planning, slice sequencing |
| product-manager | Scope, prioritization, tradeoff framing |
| quality-reviewer | Pre-acceptance review of any deliverable (code, docs, analyses, runbooks) |
| security-reviewer | Sensitive surfaces, secrets, auth |
| solution-architect | Consulting design partner — walks options, tradeoffs, principles, and recommended design artifacts before plan |
| sre | Rollout, runtime, observability |
| support-lead | Operator-facing notes, troubleshooting |
| tech-writer | Durable summary, memory wording, handback |
| test-engineer | Coverage strategy, validation depth |
| ux-specialist | Interaction states, accessibility |
<!-- generated:agents-table:end -->

The table above is derived from shared `[[agents]]` `summary` fields in `flow.toml` (agents are sorted by `name`).

### How agents get invoked

- **By commands**: `flow-define`, `flow-solution`, `flow-plan`, `flow-implement`, `flow-review`, and `flow-archive` invoke agents from their composition. See each command's "Composition" section for which agents are core vs conditional.
- **Directly**: ask the runtime to engage a specific role for a focused task, for example "have the architect look at this boundary decision" or "use the quality-reviewer to check this PR".

### Agent vs distribution-tool distinction

These agents are **personal working agents**. They define how Claude or Codex works with you when it plays a specific role. They are NOT distribution outputs designed for others to install. Project-specific review tools, such as path-nexus's review agents in `tools/agents/`, live in their project's own distribution surface.

## Architecture

- **Framework** (commands, agents, hooks, and standards) lives in user-level runtime surfaces through `flow setup user`: `~/.claude/`, `~/.agents/skills/`, and `~/.codex/`. It is active in every supported runtime session.
- **Project overlays** at `<repo>/.flow/` are opt-in per repo. Use them only where you want project-specific role assignments, memory, or run artifacts. `/flow-boot` recommends `flow setup project` by default in any repo without an overlay. To silence that recommendation for a repo permanently, ask the runtime to opt out; it will `touch .flow-skip` at the repo root. You can also run that shell command yourself.
- **Durable facts and decisions** → the active runtime's durable memory provider, when one exists; for Claude Code, that is auto-memory at `~/.claude/projects/<project-id>/memory/`; Codex currently has no Flow-managed durable memory provider
- **Transient work state** → `.flow/memory/STATE.md` (only when an overlay exists)
- **Run artifacts** → `.flow/runs/<work-id>/` (only when an overlay exists)
- Overlays stack. In nested projects, such as `~/KB/repos/path-nexus/` inside `~/KB/`, more-specific overlays override on conflicts. Memory writes go to the most-specific overlay.

## Common entry points

- "Start a fresh session" → `/flow-boot`
- "Where do I pick up?" → `/flow-resume`
- "Quick fix" → `/flow-scout`
- "I have an idea, define the outcome" → `/flow-define`
- "Multiple approaches, need to choose" → `/flow-define` → `/flow-solution` → `/flow-plan`
- "Approved requirements, shape implementation" → `/flow-plan`
- "Build something durable" → `/flow-define` → `/flow-plan` → `/flow-implement` → `/flow-review` → `/flow-archive`
- "Where do we stand?" → `/flow-status`
- "Set up flow for a new repo" → `flow setup project` (shell — ask the runtime or run from terminal)
- "Skip flow for a specific repo" → ask the runtime to opt out (will `touch .flow-skip` at repo root)
- "Read the framework operating model" → `~/.flow/source/scaffolds/default/FRAMEWORK.md`
- "Deeper maintainer docs" → `~/.flow/source/docs/`
```

## Verification

Before leaving `flow-help`, confirm:

- [ ] phase machine was rendered
- [ ] both command surfaces listed (slash commands and CLI commands), with the distinction made explicit
- [ ] all 13 agents listed with role descriptions
- [ ] core+conditional invocation pattern explained
- [ ] architecture section included
- [ ] common entry points listed by intent
- [ ] pointers to deeper docs included

## Finish Criteria

`flow-help` is done when the user has a complete-on-one-screen orientation to the framework's commands, agents, architecture, and common entry points.
