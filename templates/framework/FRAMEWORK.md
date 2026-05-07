# Flow Framework

Portable workflow contract.

## Purpose

- define reusable workflow phases
- separate framework rules from project rules
- keep project memory and run artifacts durable

## Operating model

This framework assumes two layers:

- framework rules in `.flow/`
- project-specific overrides in `.flow/PROJECT.md` and `.flow/project/`

The framework defines the shape of work. Each project defines:

- role providers
- active standards
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

This framework prefers durable files over chat.

By default, use:

1. issue tracker or explicitly assigned work item
2. `.flow/PROJECT.md`
3. relevant files in `.flow/standards/` and `.flow/project/`
4. ADRs and code
5. `.flow/memory/`

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
