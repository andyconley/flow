# flow Architecture

## Purpose

`flow` is a portable AI workflow framework with one core rule:

- **The framework** (the HOW: workflow phases, role agents, standards) is the source of truth, edited in the flow repo's `scaffolds/default/`.
- **Project overlays** (the WHAT: project-specific role assignments, memory, runs) live per-project in `<repo>/.flow/`.
- **Runtime-facing files** (`.claude/`, `.agents/skills/`, `.codex/`) are generated adapters from both layers — never hand-maintained.

This keeps durable workflow content runtime-neutral while supporting runtime-specific execution surfaces, and lets the framework be installed at the user level (active in every supported runtime session) while per-project overlays stay opt-in.

## Layer Model

`flow` operates across five layers:

1. **Machine support** at `~/.flow/` — install state, config, the source link or copy
2. **Framework source** in the `flow` repo (`scaffolds/default/`) — the canonical workflow vocabulary
3. **User overlay** at `~/.flow/user/` — personal overrides and additions that apply in every supported runtime session (opt-in)
4. **User-level install** at `~/.claude/`, `~/.agents/skills/`, and `~/.codex/` — generated adapters active in every session (built from framework + user overlay)
5. **Project overlays** at `<repo>/.flow/` and their generated adapters at `<repo>/.claude/`, `<repo>/.agents/skills/`, and `<repo>/.codex/` — per-project, opt-in

### `~/.flow/`

The machine-local install home. Contains:

- the framework at `~/.flow/source/` (the path contract — see "Install Modes" below)
- local config at `~/.flow/config.toml` (includes the `[install]` section: mode, version, installed_at)
- the user overlay at `~/.flow/user/` (see "User Overlay" below)
- support directories: `hooks/`, `logs/`

Installation and local execution support, not project truth.

#### Install Modes

`~/.flow/source` resolves to the same path in both modes, but its storage shape differs:

| Mode | Storage | Use |
|---|---|---|
| **Develop** (`install-flow.sh --develop`, default) | symlink to the user's clone | Maintainers editing framework content; edits in the clone go live immediately |
| **Release** (`install.sh`, or `install-flow.sh --release` from a clone) | real directory of copied content | Most users; rolled forward via `flow update` |

Why a single path contract: everything downstream — `flow sync`, managed manifests, hook commands, scaffold references like `~/.flow/source/scaffolds/default/commands/flow-boot.md` — resolves through `~/.flow/source/` regardless of mode. Install-mode awareness lives entirely in the install layer (`install-flow.sh`, `flow install`, `flow update`, `flow doctor`). The rest of the CLI never branches on mode.

`flow update` rolls forward a release install by staging the new tree, validating it, and atomically swapping it into `~/.flow/source/`. A failed update — at any point before the swap — leaves the existing install untouched. The window between renaming the old install aside and renaming the staging into place is a single syscall pair; failures during the swap attempt rollback.

`flow install --release` / `flow install --develop <path>` converts an existing install between modes. The clone is never deleted by either direction; the user controls its lifecycle.

#### User Overlay

`~/.flow/user/` is the user's personal customization layer. It mirrors `scaffolds/default/`'s layout:

```text
~/.flow/user/
  flow.toml              — explicit registration of overrides/additions
  agents/<name>.md       — user-authored or overriding agents
  commands/<name>.md     — user-authored or overriding commands
  hooks/flow-<name>.sh   — user-authored or overriding hook scripts
  standards/<name>.md    — user-authored or overriding standards (runtime-resolved)
  templates/<name>.md    — user-authored or overriding templates (runtime-resolved)
```

How it merges:

- **Commands, agents, and hooks are merged at sync time** by `merge_user_overlay` in `cli/sync.py`. When `flow sync claude --user` (or `flow sync codex --user`) runs, the framework's `flow.toml` is loaded and the user's `flow.toml` is layered on top:
  - Entries in the user manifest with the same `name` as a framework entry **replace** it (override).
  - Entries with a new `name` are **appended** (addition).
  - The merged manifest drives adapter generation. Generated SKILLs, agent files, and hook registrations embed or point at the user's content where applicable, and the managed manifest records `~/.flow/user/...` as the source path so the origin is auditable.
- **Standards and templates are *not* merged at sync time** — they're not embedded into adapters; they're referenced by name at runtime. The runtime resolution order is documented in `FRAMEWORK.md` under "Overlay resolution for standards and templates": project `[[replaces]]` wiring > user overlay > framework default. Projects still do not *hold* standards or templates — a `[[replaces]]` entry names a replacement that lives in the user overlay. `flow doctor` reports whether each wiring resolves on this machine.

The user overlay is opt-in. Without `~/.flow/user/flow.toml`, sync behavior is identical to the framework-only baseline. `flow doctor` reports whether the overlay is present and what it declares.

### Versioning the overlay

Every other layer flow reads has a repo behind it: the framework scaffold lives in this repo, project overlays live in their own. The user overlay is the exception — it is hand-authored content in a machine-local directory, which means no history, no diff, and no way back after a lost machine.

`flow setup user --overlay-repo <url>` closes that. Three cases, and none of them may discard content:

- **already a repo** — report and leave alone. Re-pointing a remote is deliberate, not a side effect of setup.
- **absent or empty** — clone. This is the new-machine path, and it is what makes the overlay portable.
- **has content, no `.git`** — `git init` in place, add the remote. Never clone over existing work.

Setup initializes; it does not commit. Who commits is a convention rather than a mechanism, documented in `FRAMEWORK.md`: the agent that edits overlay content commits it in the same turn, because the human who owns that content is not the one editing it.

`cli/overlay.py` holds the status query, kept out of `diagnostics.py` so `doctor` stays a reporter and the status stays unit-testable. Up to four git calls, all local, all bounded at two seconds, skipped entirely when there is no overlay: `rev-parse --show-toplevel` finds the work tree, `check-ignore` catches an overlay the surrounding repo excludes, `status --porcelain=v2 --branch` carries the dirty list, the branch name, the upstream ref, and the ahead-count together, and `config --get remote.origin.url` gets the remote URL. Reading the branch from that header rather than `rev-parse --abbrev-ref HEAD` is deliberate — rev-parse returns the literal string `HEAD` on a detached head and fails outright before the first commit, so both states would be reported wrongly.

The status takes a `quick` flag, and the per-prompt advisory hook is the only caller that sets it. It drops the fourth call: the hook needs to know whether anything is unpushed, which the `--branch` header already answers via the upstream ref, so paying ~45ms per prompt to also learn the remote's URL buys nothing it uses. The cost is one distinction the hook no longer draws — a repo with a remote but no upstream reads the same to it as a repo with no remote — and `doctor`, which runs on demand and uses the full status, still separates them. `quick` is why `remote` must never be read by a caller that might pass it: `None` then means "not asked" rather than "not configured", and `setup`'s differing-remote check would silently start adding an origin that already exists.

Version 2 of the porcelain format is a deliberate choice over v1, and not a free one. v1's `## branch...upstream [ahead N]` header does not name the upstream separately from the branch, which is the field the `quick` path exists to read; v2 emits `branch.upstream` and `branch.ab` as their own lines and omits both when no upstream is set. The cost is that v2's entry lines drop v1's fixed-width `XY ` prefix in favor of variable field counts — eight fields before the path for an ordinary change, nine for a rename (whose two paths are tab-separated), ten for an unmerged entry, one for an untracked one. Paths routinely contain spaces, so the path has to be split off by field count. A fixed-offset slice carried over from v1 returns field soup, and it returns it silently, which is why every entry type has its own test.

The environment for those calls strips ambient `GIT_DIR`/`GIT_WORK_TREE`-style variables (set inside git hooks, and by some tooling) so a cwd-relative command cannot be redirected at the wrong repository, but otherwise inherits the user's environment. An earlier version replaced the environment entirely; without `HOME`, git cannot read `~/.gitconfig`, so `core.excludesFile` goes unapplied and `status` reports files the user's own git would ignore. When a git call fails for any reason, the status says `unreadable (git error)` rather than synthesizing a plausible-looking clean or detached state — a diagnostic that states a false condition is worse than one that admits it does not know.

### Framework Repo (`scaffolds/default/`)

The framework source. Contains:

- workflow command contracts under `commands/`
- role agent definitions under `agents/`
- shared standards library under `standards/` (flow-authored standards) and `standards/vendor/` (verbatim mirrors of upstream specs that flow depends on)
- memory placeholders under `memory/`, form templates under `templates/`
- the runtime adapter manifest at `flow.toml` (also records declared dependencies on upstream standards via `[standards.<name>]` blocks)

This defines what the user-level install generates and what `flow setup project` copies into a repo's overlay.

#### Vendored Upstream Content

Some flow standards are pinned to external specifications maintained outside the project (e.g., Conventional Commits). Flow handles these via a *vendored mirror* pattern rather than runtime fetch or git submodules:

- The upstream spec is copied verbatim into `scaffolds/default/standards/vendor/<spec-name>-<version>.md`, with an attribution header (`<!-- VENDORED VERBATIM -->`) naming the source repo, pinned commit SHA, and license.
- A flow-authored standard at `scaffolds/default/standards/<topic>.md` cites the vendored mirror and distills the rules agents actually need at decision time.
- The dependency is declared in `flow.toml` under `[standards.<topic>]` with `upstream`, `upstream_version`, `vendored_sha`, and `vendored_at`.
- A maintainer script under `scripts/refresh-<topic>.py` resolves the latest upstream content, diffs against the vendor mirror, and updates both the mirror and the `flow.toml` metadata in one step. Consumers never run this — they receive whatever's vendored in the flow release they installed.

Why this shape:

- **No runtime fetch.** The framework works offline; agents never need to reach the network to consult a standard.
- **No submodule fragility.** `install-flow.sh` (both develop and release modes) treats the vendor mirror as ordinary scaffold content.
- **Auditable.** The pinned SHA + date in `flow.toml` makes it trivial to confirm what version of an external spec a given flow install is bound to.
- **The `vendor/` boundary is the editing contract.** Anything under `vendor/` is verbatim upstream content; never hand-edit. Flow-authored extensions and project-specific overlays live elsewhere.

### User-Level Install (`~/.claude/`, `~/.agents/skills/`, `~/.codex/`)

Generated by `flow setup user` (or `flow sync claude --user` / `flow sync codex --user`). Active in every supported runtime session regardless of cwd.

Contains Claude surfaces:

- `~/.claude/skills/flow-*/SKILL.md` — generated from framework commands
- `~/.claude/agents/*.md` — generated from framework agents
- `~/.claude/hooks/flow-*.sh` — copied from the framework's reusable hook scripts
- `~/.claude/settings.json` — merged with managed flow hook entries (unmanaged settings preserved)
- `~/.claude/flow.managed.toml` — managed-file manifest for drift tracking

Contains Codex surfaces:

- `~/.agents/skills/flow-*/SKILL.md` — generated from framework commands
- `~/.codex/agents/*.toml` — generated from framework agents
- `~/.codex/hooks/flow-*.sh` — copied from the framework's reusable hook scripts
- `~/.codex/hooks.json` — merged with managed flow hook entries (unmanaged hook handlers preserved)
- `~/.codex/flow.managed.toml` — managed-file manifest for drift tracking

The session-start hook is responsible for detecting whether the current project has a `.flow/` overlay; commands invoked in non-overlay projects still work, just without project-specific context.

### `<repo>/.flow/` (Project Overlay)

Per-project source of truth for **project-specific** content only:

- `PROJECT.md` — role assignments, sources of truth, project distinctives
- `memory/STATE.md` — transient work state (what is in flight, blocked, pending). Durable facts and decisions live in Claude Code auto-memory at `~/.claude/projects/<project-id>/memory/`, not here.
- `runs/<work-id>/...` — per-task execution artifacts
- `runs/<work-id>/run.json` — C-lite current-state projection for gated workflow runs
- `runs/<work-id>/events.jsonl` — append-only transition history for that run

The framework content (commands, agents, standards) is NOT duplicated here in the user-level install model — it's served from the user-level install. Projects only opt into the overlay layer when they actually need project-specific role assignments, memory, or run artifacts.

Workflow run state is dependency-free and local to the project overlay. `flow run transition` owns lifecycle writes against `run.json` and `events.jsonl`; `/flow-*` commands call that CLI when they cross critical gates. Existing run folders without `run.json` remain readable as `legacy/inferred` and are not migrated as a side effect of status or resume.

### Stacked Overlays

When projects nest (e.g., `~/KB/repos/path-nexus/` inside `~/KB/`), overlays stack. flow walks up the directory tree from the current project and merges `.flow/` overlays from all ancestor projects.

Merge rules:

- More-specific overlays override on conflicts (path-nexus overrides KB)
- Memory writes always go to the most-specific overlay
- Reads merge across all stacked levels — `flow-status` surfaces project-level state prominently while listing parent-overlay state as parent context

## Source-of-Truth Rule

The operational rule, by layer:

- **Framework content** (workflow commands, role agents, shared standards): edit in the flow repo's `scaffolds/default/`, then re-run `flow sync claude --user` (and `flow sync codex --user`) to push changes to the user-level install.
- **Project overlay content** (PROJECT.md, memory, runs): edit in `<repo>/.flow/`. Nothing needs regenerating — a project's overlay holds its own context and work, not runtime adapters. Project-level sync was retired; `flow project migrate` removes what an earlier one left behind.
- **Never hand-maintain generated surfaces** — `~/.claude/skills/flow-*`, `<repo>/.claude/agents/*`, etc. are generated adapters. If you find yourself wanting to edit them directly, the change belongs in the corresponding source layer.

The framework reinforces this with generated markers in every adapter file, managed manifests at each runtime root, and a `PostToolUse` reminder hook that nudges editors back to source when a managed file is modified directly.

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

`flow-define` is the early requirements lane: it turns feature or architectural-capability ideas into approved requirements, with research and adversarial review before routing to `flow-solution` or `flow-plan`. Bug-shaped work remains in `flow-plan` until Flow grows a separate defect-definition lane.

### Agents

Agents are registered once and adapted per runtime.

Reason:

- `.flow/agents/*.md` are the durable role contracts
- shared `[[agents]]` entries in `flow.toml` name the source file, summary, and semantic model tier
- each runtime needs a different generated shape for model and effort controls

Current examples:

- Claude receives generated `.claude/agents/*.md` files with manifest-resolved `model` and `effort`
- Codex receives generated `.codex/agents/*.toml` files with `developer_instructions`, `model`, and `model_reasoning_effort`

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

Current Claude generation includes:

- skills
- agents
- hooks
- managed settings merge
- managed manifest

### Codex

Current Codex generation targets native skill, agent, and hook surfaces:

- skills
- agents
- hooks
- managed manifest

This keeps Flow as an adapter framework: Flow writes native Codex configuration
files from the shared manifest, then `flow doctor` reports whether the static
files are present and configured.

## Upgrade Model

There are currently two project-evolution paths:

- `flow setup project` for first-time scaffold, and for repairing a core file
  that has gone missing since — it is idempotent and never overwrites
- `flow project migrate` for reconciling an overlay built before the scaffold
  was thinned

`flow refresh project` used to be the second of these and is retired.

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
