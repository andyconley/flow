# flow Architecture

## Purpose

`flow` is a portable AI workflow framework with one core rule:

- the source of truth lives in `repo/.flow`
- runtime-facing files such as `.claude/` or `.codex/` are generated adapters

This keeps durable workflow content, standards, commands, and role definitions in a runtime-neutral form while still supporting runtime-specific execution surfaces.

## Layer Model

`flow` is split into three layers:

1. machine-local support in `~/.flow/`
2. reusable framework source in the `flow` repo
3. repo-local instantiated framework in `repo/.flow`

### `~/.flow/`

This is the machine-local install home. It contains:

- the linked framework repo at `~/.flow/source`
- local config at `~/.flow/config.toml`
- support directories such as `hooks/`, `user/`, and `logs/`

This layer is about installation and local execution support, not project truth.

### Framework Repo

The framework repo contains:

- the CLI
- reusable hook scripts
- the project scaffold template under `scaffolds/default/`
- the runtime adapter manifest under `scaffolds/default/flow.toml`
- tests and maintainer docs

This layer defines what a project gets when it runs `flow setup project` or `flow refresh project`.

### `repo/.flow/`

This is the project-local source of truth. It contains:

- standards
- commands
- agents
- project overlays
- memory
- templates
- the adapter manifest `flow.toml`

This is the layer collaborators should edit directly.

## Source-of-Truth Rule

The operational rule is:

- edit `repo/.flow/*`
- regenerate runtime adapters
- do not hand-maintain generated runtime surfaces unless you are intentionally porting changes back to `.flow`

The framework reinforces this with generated markers, managed manifests, and runtime reminder hooks.

## Adapter Model

The adapter model exists because runtimes do not consume the same shape of content.

### Commands

Commands are runtime-adapted.

Reason:

- `.flow/commands/*.md` are generic workflow contracts
- each runtime may need different wrapper metadata, invocation behavior, or packaging

Current examples:

- Claude receives generated `SKILL.md` files with explicit frontmatter
- Codex receives generated `SKILL.md` files with a narrower wrapper surface

### Agents

Agents currently sync near-verbatim for Claude.

Reason:

- `.flow/agents/*.md` are already close to Claude's usable project-agent shape
- adding another wrapper layer now would mostly duplicate content and increase drift risk

This may change later if runtimes need materially different agent metadata or behavior.

## Managed vs Unmanaged Boundaries

Generated runtime files are tracked in runtime-specific managed manifests:

- `.claude/flow.managed.toml`
- `.codex/flow.managed.toml`

These manifests let `flow` distinguish:

- managed files it is allowed to replace or remove
- unmanaged files it should preserve

Current behavior:

- generated managed files are updated in place
- stale managed files are removed
- unmanaged conflicting files cause sync to stop with a conflict

## Runtime Split

### Claude

Current Claude generation is the richer runtime:

- skills
- agents
- hooks
- managed settings merge
- managed manifest

This exists because Claude currently has the clearest runtime contract for all of these surfaces.

### Codex

Current Codex generation is intentionally narrower:

- skills
- managed manifest

This proves `flow` is not Claude-only without inventing runtime features that are not yet well-defined for Codex in this framework.

## Upgrade Model

There are currently two project-evolution paths:

- `flow setup project` for first-time scaffold
- `flow refresh project` for missing-file refresh

What does not exist yet:

- content-aware merges for changed project files
- guided migration assistants for older `.flow` instances

## Testing Model

The `flow` repo currently uses a lightweight CLI-level test suite rather than deep unit mocking.

Reason:

- the important behavior is end-to-end scaffold and sync behavior
- managed-file semantics are easiest to verify through real temp repos
- runtime generation drift is a contract behavior, not just a helper-function detail

See:

- [/Users/andyconley/src/flow/tests/test_flow.py](/Users/andyconley/src/flow/tests/test_flow.py)
