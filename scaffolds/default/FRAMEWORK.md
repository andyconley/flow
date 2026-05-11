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
2. plan
3. implement
4. review
5. archive or resume

Not every task needs every phase. Small work should stay small.

## Core commands

- `/flow-boot`
- `/flow-scout`
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
- `memory/` - cross-session state
- `runs/` - per-work-item artifacts

## Canonical sources

This framework prefers durable files over chat. When stacked overlays exist, more-specific overlays win on conflicts.

By default, use:

1. issue tracker or explicitly assigned work item
2. `.flow/PROJECT.md` (read from every stacked overlay level)
3. relevant files in `.flow/standards/` and `.flow/project/`
4. ADRs and code
5. `.flow/memory/` (read from every stacked overlay level)

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
