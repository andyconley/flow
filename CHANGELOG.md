# Changelog

All notable changes to flow are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

flow's behavioral source-of-truth lives in `scaffolds/default/` (commands, agents, standards). Doc-only commits to those files that materially change how agents engage at runtime are treated as MINOR bumps even though they are `docs(...)` by Conventional Commits type — the docs *are* the behavior.

## [Unreleased]

### Fixed

- **Current Codex standalone-skill discovery.** Codex adapters now generate
  required `name` and `description` frontmatter under `.agents/skills/` while
  retaining `.codex/flow.managed.toml` for Flow's ownership tracking. Existing
  manifests that declare the former `.codex/skills` path migrate on their next
  sync; only previously managed legacy files are removed. Claude generation is
  unchanged.

## [0.6.1] — 2026-05-15

### Changed

- **Release roster is now a blacklist, not a whitelist** (backlog P8 fix). Previously `install-flow.sh` and `cli/flow.py`'s `_populate_release_dir` enumerated specific dirs and files to include (`RELEASE_COPY_DIRS = ("cli", "scaffolds", ...)`, `RELEASE_COPY_FILES = ("README.md", "CHANGELOG.md")`). When a new top-level item was added in version B and a user updated from version A directly to version C, A's whitelist didn't know about the new item, and it was silently omitted from the release — observed concretely when v0.4.5 added `CHANGELOG.md`. The roster now copies every non-dotfile top-level entry **except** the explicit excludes (`tests/`, `install-flow.sh`, `install.sh`, plus the existing recursive-cleanup list for `__pycache__`/`.claude`/`.codex`/`.git`/`*.pyc`/`.DS_Store`). New top-level files added in future versions are picked up automatically by older clients doing the swap.

### Why this is 0.6.1 (patch)

Bug fix. No new behavior visible to existing users (the same set of files lands in a release install today as before this commit — the difference matters for *future* additions, where the blacklist approach silently does the right thing).

### Resolved from backlog

- **P8: Two-phase update for roster changes** — addressed by removing the need for a "two-phase update" entirely: the new blacklist-based roster is forward-compatible, so old clients doing the swap include any new top-level files from the new version without knowing what they are.

## [0.6.0] — 2026-05-15

### Added

- **User-level overlay at `~/.flow/user/`** — personal customizations that survive framework updates. Lets you override the framework's built-in commands and agents, *and* add wholly new ones (your own `/flow-jira-status` and friends) without forking. Resolves backlog P2.
- The overlay mirrors `scaffolds/default/`'s layout:
  ```
  ~/.flow/user/flow.toml     — explicit registration of overrides/additions
  ~/.flow/user/agents/*.md   — overriding or new agents
  ~/.flow/user/commands/*.md — overriding or new commands
  ~/.flow/user/standards/*.md — overriding or new standards (runtime-resolved)
  ~/.flow/user/templates/*.md — overriding or new templates (runtime-resolved)
  ```
- **Merge semantics at sync time** (commands + agents): when `flow sync claude --user` (or `--codex`) runs, the framework's `flow.toml` is loaded and the user's `flow.toml` is layered on top. Entries with the same `name` replace the framework entry (override); new names append (addition). Implemented in `merge_user_overlay()` in `cli/flow.py`. The merged manifest drives adapter generation, and the managed manifest records `~/.flow/user/...` paths so origin is auditable.
- **Runtime resolution convention** (standards + templates): not merged at sync time — referenced by name and resolved at runtime in **most-specific-wins** order: project overlay > user overlay > framework default. Documented in `FRAMEWORK.md` under "Overlay resolution for standards and templates."
- **`flow doctor` reports user overlay state** — lists the overlay's commands and agents if present, or notes "none" if `~/.flow/user/flow.toml` is absent.

### Why this is a minor bump (0.6.0)

This is the second new behavior added to the CLI after v0.5.0's CHANGELOG preview. It changes what `flow sync --user` does: previously framework-only; now framework + user overlay. Existing installs without `~/.flow/user/flow.toml` see identical behavior (regression test confirms). New behavior is fully additive — no breaking change.

### Resolved from backlog

- **P2: User-level overrides via `~/.flow/user/`** — shipped. Standards/templates left as runtime-resolution convention rather than a new generation pipeline, per the c-lite scope decision.

## [0.5.0] — 2026-05-15

### Added

- **`flow update --check` now previews the CHANGELOG section for the available version.** After printing the version comparison, the command fetches `CHANGELOG.md` from the remote at the new tag (via a sparse partial-clone — `--filter=blob:none --no-checkout --sparse` + `sparse-checkout set CHANGELOG.md`, so only the one file is actually downloaded) and prints the `## [<version>]` section. Users now know *what* they'd be updating to, not just that an update exists. Failure to fetch or parse falls back silently — version comparison remains the primary signal.

### Why this is a minor bump (0.5.0 rather than 0.4.6)

The patch trajectory (0.4.x) was about install/update mechanics — getting the scaffolding right. This is the first commit that adds a *new behavior* to the CLI rather than fixing or refining existing behavior. `flow update --check` previously answered "is there an update?"; it now also answers "what's in it?". Different question, different value, hence the minor bump.

## [0.4.5] — 2026-05-15

### Changed

- **`CHANGELOG.md` now ships in the release install roster.** Previously, `flow install --release`, `flow update`, and the bootstrap `install.sh` copied `README.md` but not `CHANGELOG.md` — release-mode users couldn't read their installed framework's version history without going to GitHub. Both `install-flow.sh`'s copy loop and `cli/flow.py`'s `RELEASE_COPY_FILES` updated. Existing release-roster test extended to assert `CHANGELOG.md` lands.

## [0.4.4] — 2026-05-15

### Added

- **Portable bootstrap installer** at the repo root: `install.sh`. Single-command install for consumers — `curl -fsSL https://raw.githubusercontent.com/andyconley/flow/main/install.sh | bash` queries the configured flow remote for the latest semver tag, shallow-clones it to a temporary directory, delegates to `install-flow.sh --release`, and cleans up. No prior cloning required. Resolves backlog P5.
- `FLOW_REPO_URL` env var override for `install.sh` — primarily for tests; lets the installer target a non-default remote.
- `FLOW_VERSION_OVERRIDE` env var support in `install-flow.sh` — lets a caller (the bootstrap installer) pin the exact version label, preserving caller intent even when the cloned commit has multiple tags referencing it.

### Changed

- README "Quick Install (recommended for consumers)" section added at the top of the install documentation. The existing "Local Install" section is now scoped to maintainer/contributor flow.

### Resolved from backlog

- **P5: Single-command portable installer for consumers** — adoption barrier removed.

## [0.4.3] — 2026-05-15

### Added

- **`scripts/regenerate-flow-help.py`** generates the three `flow-help.md` tables (slash commands, CLI commands, agents) from `flow.toml`. Supports `--check` for drift detection — exits 1 with a unified diff if regeneration would change anything.
- `summary` field on each `[[claude.commands]]` and `[[claude.agents]]` entry — the short label rendered in the flow-help tables (distinct from the longer `description` used for skill/agent metadata).
- `[[help.cli_commands]]` array in `flow.toml` — `invocation` + `summary` per CLI command, used to build the CLI-commands table.

### Changed

- `scaffolds/default/commands/flow-help.md` now uses HTML-comment markers around the three generated tables. Hand-editing the tables is no longer supported — edit `flow.toml` and re-run the generator. The phase machine diagram, agent-invocation prose, architecture section, and verification checklist remain hand-maintained.
- `[[claude.commands]]` in `flow.toml` reordered into workflow-narrative sequence (boot → scout → solution → plan → implement → review → archive → resume → status → init-project → help) so registration order matches rendered help-table order.

### Resolved from backlog

- **P6: flow-help.md drift from CLI/agent surfaces** — single source of truth wired up; new test catches forgotten regeneration at PR/CI time.

## [0.4.2] — 2026-05-15

### Fixed

- `flow install --release` no longer leaks a stale `~/.flow/source.old` symlink. Previous behavior: converting from develop mode renamed the develop-mode symlink to `source.old`, and the post-swap cleanup silently failed to delete it because `shutil.rmtree(path, ignore_errors=True)` doesn't follow symlinks. The leftover then caused the next `flow update` to crash with `[Errno 20] Not a directory`. Fix: new `_remove_path()` helper routes symlinks/files through `os.unlink()` and uses `shutil.rmtree()` only for real directories. All install/update cleanup call sites updated.

## [0.4.1] — 2026-05-15

### Changed

- **Engagement-discipline hardening across the gated workflow.** `flow-solution`, `flow-plan`, `flow-implement`, `flow-review`, and the `solution-architect` agent now include `<HARD-GATE>` blocks at the top that prevent the agent from producing structured output until the engineer has confirmed a restated problem and explicit unknowns. Adopts the pattern from the superpowers `brainstorming` skill without taking a dependency.
- **`flow-solution` and `flow-plan` restructured into three explicit phases** (Engagement → Solutioning/Shaping → Capture) with a hard checkpoint between Phase 1 and Phase 2. The "Always emit the structured output" instruction moved under the Capture phase so it no longer competes with the engagement-first discipline.
- **`flow-implement` Phase 1 (Requirements)** now requires a user-facing check-in before proceeding to current-state inspection. Ambiguities must be surfaced to the engineer and resolved or explicitly waived; "I confirmed it myself" is not enough.
- **`flow-review` Verdict** now requires explicit comprehension of both the changed artifacts and the original plan/acceptance criteria before producing a judgment.

## [0.4.0] — 2026-05-15

### Added

- **Two-mode install.** `install-flow.sh --develop` (default, symlink to clone — current behavior preserved) and `install-flow.sh --release` (real copied directory, version-stamped via `git describe`). Both modes share the `~/.flow/source/` path contract so all downstream code (sync, managed manifests, hook commands) is mode-agnostic. Excludes `.git/`, `tests/`, `install-flow.sh`, `__pycache__/` from the release copy.
- **`flow update [--check] [--resync] [--remote URL]`.** Atomic version rollforward for release-mode installs. Fetches the latest semver tag from the configured remote (`https://github.com/andyconley/flow.git` by default), stages the new tree, validates it, then atomically renames into place. `--resync` runs `flow sync claude --user && flow sync codex --user` after applying. Develop mode prints manual pull-and-resync instructions instead.
- **`flow install --release`** converts a develop install to a release install in place. The develop-mode clone is **not** deleted — the user controls its lifecycle.
- **`flow install --develop <clone-path>`** converts a release install to a develop install symlinked at the given clone.
- **Install metadata in `~/.flow/config.toml`.** New `[install]` section records `mode`, `version` (release), `source_target` (develop), `remote` (release), and `installed_at` timestamp.
- **`flow doctor` install section.** Reports mode (develop/release), version or source-target as applicable, installed_at, and how to query for updates.
- **Conventional Commits adopted as a declared upstream dependency.** Flow-authored standard at `standards/git-commits.md` cites a verbatim vendored mirror at `standards/vendor/conventional-commits-1.0.0.md`, pinned to upstream commit `7d293dc59e88abc8ce6c6698344d4da518ff3f27` with MIT license preserved. Declared in `flow.toml` under `[standards.git-commits]`. Maintainer refresh script at `scripts/refresh-conventional-commits.py`. Cited by `lead-developer.md`, `quality-reviewer.md`, `flow-implement.md`, and `flow-scout.md` so commit messages are governed by the standard at every commit-writing step.
- **Solutioning workflow.** New `/flow-solution` slash command (optional pre-plan step for option exploration), new `solution-architect` agent (consultative architect for engineers translating approved requirements into a technical design), three new standards (`solutioning-criteria.md`, `solutioning-decisions.md`, `solutioning-risks.md`), and a `spike-template.md` (Form A smallest-viable / Form B full / Investigation variants).

### Changed

- `flow help` (and `/flow-help`) reflects the additions: lists `flow install`, `flow update`, `/flow-solution`, and `solution-architect`. Agent count bumped from 12 → 13. Phase machine diagram shows `[solution]` as an optional pre-plan step.
- `flow doctor` source-of-truth language: "machine, install, user-level, and project-level state."
- Test runner clears `FORCE_COLOR` and sets `NO_COLOR=1` so assertions on plain-text CLI output are stable under Python 3.14's colored argparse help.

### Resolved from backlog

- **P4: Framework update workflow for an installed user-level surface** — `flow update` ships this. Detection-by-doctor is partial (`flow update --check` is the query path; `flow doctor` doesn't auto-fetch to avoid surprise network calls).

## Earlier history

Commits before `v0.4.0` predate the CHANGELOG. The git log is the authoritative record for those.

[Unreleased]: https://github.com/andyconley/flow/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/andyconley/flow/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/andyconley/flow/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/andyconley/flow/compare/v0.4.5...v0.5.0
[0.4.5]: https://github.com/andyconley/flow/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/andyconley/flow/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/andyconley/flow/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/andyconley/flow/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/andyconley/flow/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/andyconley/flow/releases/tag/v0.4.0
