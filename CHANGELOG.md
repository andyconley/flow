# Changelog

All notable changes to flow are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

flow's behavioral source-of-truth lives in `scaffolds/default/` (commands, agents, standards). Doc-only commits to those files that materially change how agents engage at runtime are treated as MINOR bumps even though they are `docs(...)` by Conventional Commits type — the docs *are* the behavior.

## [Unreleased]

No unreleased changes.

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

[Unreleased]: https://github.com/andyconley/flow/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/andyconley/flow/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/andyconley/flow/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/andyconley/flow/releases/tag/v0.4.0
