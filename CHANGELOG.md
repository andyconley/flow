# Changelog

All notable changes to flow are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

flow's behavioral source-of-truth lives in `scaffolds/default/` (commands, agents, standards). Doc-only commits to those files that materially change how agents engage at runtime are treated as MINOR bumps even though they are `docs(...)` by Conventional Commits type — the docs *are* the behavior.

## [Unreleased]

### Added

- **Usage advisory in the workflow commands** (token-advisory chunk 9) —
  the first place the usage store influences agent behavior rather than
  just answering queries. Doc-only, per this file's own convention that
  scaffold command docs *are* the behavior: `flow-boot` gains a usage
  advisory step (Codex capacity verbatim when present; any session at
  25%+ carry), `flow-status` gains a session-cost step (this session's
  ctx/carry via `flow cost active`, matched by cwd, ambiguity said aloud
  — deliberately the *session's* cost, since the store has no run
  concept), and `flow-plan`/`flow-solution` gain a cost posture check in
  their shaping phases (mentioned alongside the lane/chunk
  recommendation, never as it). Posture is informational-only and stated
  inline in every edit: advisory lines never block a phase, never change
  a default, and absence of data means silence, not a warning.

- **`flow cost active`** (token-advisory chunk 8) — per-active-session
  context percentage, carry above session start, idle, and a
  `/clear`-or-`/compact` recommendation, worst carry first. Supersedes
  `~/bin/token-report --active` (that tool is now deprecated machine-side;
  its one remaining consumer, the Stop hook's `--verdict`, migrates in a
  later chunk). Store-backed instead of re-parsing transcripts: runs the
  incremental Claude harvest AND a normalize pass before querying — the
  normalize step is load-bearing, since a freshly harvested turn exists
  only in `turn_raw` until projected. Semantics carried over from
  token-report with two deliberate divergences: liveness/idle come from the
  latest main-thread turn's timestamp rather than transcript file mtime
  (misses a session where the user typed but no assistant turn landed yet —
  bounded by one turn), and a session is one row even where its subagent
  files would have surfaced as separate rows. Context math is main-thread
  only (`is_subagent = 0`) — the store interleaves sidechain turns where
  the old per-file read never did. The statusline's
  `/tmp/claude-window-<sid>` files are still read for exact window sizes,
  snapped to the two real windows; otherwise inferred (>190K observed ⇒
  1M), marked `~` in the table. Validated side-by-side against
  `token-report --active` on live sessions: identical ctx/carry/
  recommendation on every commonly-visible session.

### Fixed

- **User-overlay skills' generated edit hint pointed at a file that doesn't
  exist.** `render_skill_from_command` hardcoded
  ``Edit `.flow/<source>` and run `flow sync claude`​`` regardless of
  origin; a user-overlay command's source lives under `~/.flow/user/` and
  only ever syncs in `--user` mode. Found while moving the first real
  personal command (`session-hygiene`, machine-local, not in this repo)
  onto the overlay mechanism. The three sibling render sites (codex
  skills, both agent renderers) have the same defect but take bare string
  arguments — deferred to a follow-up rather than folded in here.
- **Genuine last-write-wins for repeated `ai-title` records** (token-advisory
  chunk 7). Chunk 6 shipped `ai-title` as "first one wins, forever"
  (`WHERE title IS NULL`) and documented the divergence from a true
  last-write-wins as inert on real data. This chunk fixes it — and the first
  design didn't survive contact with real data either: it assumed title
  records carry their own `timestamp` to compare, and they don't (all 6,340
  real `custom-title`/`ai-title` records sampled carry exactly
  `{type, aiTitle|customTitle, sessionId}`, nothing else). What real data
  does have is timestamps on *adjacent* records, and JSONL is append-only —
  so schema v4 adds `session.last_seen_ts`, a running high-water mark
  advanced from every timestamped record, and an `ai-title`'s *effective*
  timestamp is that mark at the moment its line is processed, compared
  against `title_ai_ts` (the effective timestamp of the currently-accepted
  auto-title). `title_source` records whether `custom` or `ai` last won;
  a `custom-title` locks out every future `ai-title` permanently. Known,
  accepted limitation: back-to-back `ai-title` records with nothing
  timestamped between them tie, and the first of the tied cluster wins —
  this is not a full last-line-wins reconstruction, but it correctly
  resolves genuine time-separated re-titling and the one real case of a
  session's title records spanning two files. All three new columns are
  NULL on migration; one `flow harvest claude --backfill` run re-derives
  them for existing sessions. Review caught two real defects in the first
  cut, both fixed with reproduction tests: a repeated `--backfill` silently
  flipped multi-`ai-title` sessions back to their *first* auto-title
  (after a full pass `last_seen_ts` holds the file-wide maximum, so a
  replay handed the first `ai-title` an effective timestamp newer than the
  stored one — `_reset_claude_watermarks` now clears the derived title
  state so every replay is a genuine first pass), and an all-untimed
  cluster accepted the *last* `ai-title` rather than the documented first
  (every untimed record re-qualified through the both-NULL branch; a
  `title_source IS NULL` leg makes acceptance genuinely once-only there).
- **`cwd` now fills from any record type that carries it**, not just the
  identity-establishing one. A file whose first record is a title line
  (which carries no `cwd`) previously left `session.cwd` NULL forever,
  silently weakening `flow cost sessions`' title→cwd→id label fallback for
  that session. Repaired retroactively by the same `--backfill` replay.
- **`--limit N` on `flow cost sessions`** (default 20, `--limit 0` for
  unlimited), applied in the query itself so `--json` and the table always
  see the identical capped set. `--all` alone now shows the 20 most recent
  sessions ever; `--all --limit 0` is the explicit everything escape hatch.

- **`flow harvest codex`** — the first collector for the usage store (token-advisory
  chunk 3). Incrementally reads `~/.codex/sessions/**/*.jsonl` into the raw
  layer (`session`, `turn_raw`, and a new `agent_activity_raw` table), resuming
  per file from the `harvest` table's watermark. Ensures the store on first
  run rather than requiring `flow setup machine` first. No normalization, no
  advisory behavior, no read surface — later chunks.
- Schema migration v2: `agent_activity_raw` (coarse activity log for events
  that carry no token usage — first observed as Codex's cloud/background-agent
  telemetry, which has no local transcript to attach usage to) and
  `session.source_path` (a direct pointer a resumed harvest needs to resolve
  which session a batch belongs to, without inferring it from a child row that
  may not exist yet).
- **`flow normalize`** (token-advisory chunk 4) — projects every harness's raw
  `turn_raw` records into `turn_norm`'s shared, disjoint-token convention, so
  nothing above that layer needs to know Codex reports `cached_input_tokens`
  as a *subset* of `input_tokens` while Claude's cache buckets are disjoint
  and additive. Only rows with no current-version `turn_norm` counterpart are
  (re)computed — a separate command from `flow harvest codex`, since appending
  new raw data and recomputing derived data have different cost profiles and
  a rule change can touch every row. Schema migration v3 adds
  `capacity_secondary_*` columns to `turn_norm`, mirroring
  `capacity_primary_*` — real data showed Codex's `rate_limits.secondary`
  populated in 7.7% of rows on a 16,260-row corpus, not "null in every
  sample" as originally found. `_V1` and `_V2` untouched; `_V2` is already
  applied on real installs and could not be edited in place this time.
- **`flow harvest claude`** (token-advisory chunk 5) — the second collector.
  Incrementally reads `~/.claude/projects/**/*.jsonl`, deduplicating by
  `requestId` (a single API response is written as several JSONL lines; the
  natural key is `requestId` itself, no composite needed the way Codex's
  `turn_id:source_line_no` was). `_EXTRACTORS["claude"]` added to
  `normalize.py` in the same chunk — direct mapping, no subtraction, since
  Claude's token fields are already disjoint. `cli/jsonl_watermark.py` and
  `cli/session_lookup.py` extracted from `codex_collector.py` (both entirely
  harness-agnostic) rather than duplicated into the new collector.
- **`flow cost summary` / `flow cost sessions`** (token-advisory chunk 6) —
  the first commands that read `turn_norm` instead of writing to it.
  `summary` groups token totals by `(harness, model)` within a window
  (`--days N`, default 7; `--all` for everything), plus Codex's most recent
  capacity reading as a separate gauge line — a snapshot, not a sum, so it's
  never blended into the token totals and is labeled by the window size
  actually stored rather than by `primary`/`secondary` — `usage_store.py`'s
  `_V3` migration documents that those names don't reliably mean "the short
  window" and "the long window" (real data shows both a 300-minute and a
  10080-minute value under the `primary` name alone).
  `sessions` groups by session, most recently active first, with a
  three-tier label fallback (`title` → `cwd` → a short id). Both views are
  one pure query function returning a list of dicts, rendered two ways —
  an aligned table by default, `--json` for the same result (`{"rows":
  [...]}`, with `summary` adding a sibling `"capacity"` key) — rather than
  two separate code paths that could drift from each other.
- **Claude title capture and backfill**, in the same chunk. `custom-title`
  and `ai-title` JSONL records now populate `session.title`, a column that
  has existed since the schema's first version but that no collector wrote
  to. Mirrors `token-report`'s precedence (`custom-title` always wins;
  `ai-title` only fills a gap) but as two idempotent, order-independent SQL
  `UPDATE`s instead of an in-memory single pass, since this collector runs
  incrementally across many separate invocations rather than once per file.
  `flow harvest claude --backfill-titles` rewinds every already-recorded
  file's watermark and replays it through the normal pipeline so already-
  harvested sessions pick up titles retroactively — `turn_raw`'s natural-key
  uniqueness makes the replay a free no-op for turns already recorded, so
  this reuses the whole validated harvest path rather than a narrower
  title-only scanner. Validated against the real local corpus: 162 of 352
  real Claude sessions picked up a title on the first backfill run.

### Changed

- **`flow harvest claude --backfill-titles` renamed to `--backfill`**
  (token-advisory chunk 7) — breaking for anything invoking the old flag
  name. The replay mechanism now repairs titles, `cwd`, and title
  provenance in one pass, so the title-specific name stopped being honest.
  `COLLECTOR_VERSION` bumped 1 → 2 (informational; nothing branches on it) —
  this chunk is the first to change what the Claude collector derives from
  already-committed lines.
- **`flow cost sessions` now caps at the 20 most recent sessions by
  default** — previously unlimited. A behavior change to existing output
  (including `--json`), not just a new flag: any consumer of the
  uncapped listing needs `--limit 0` to keep it.

### Fixed

- Two collector bugs found only by validating against a real 83-file, 6-month
  Codex session corpus rather than synthetic fixtures alone, both silent —
  neither raised an error or failed a test until the real-data counts were
  cross-checked by hand:
  - A subagent's session file carries a second `session_meta` record shortly
    after its own — a verbatim copy of the *parent's*, injected so the
    child's transcript is self-contained (confirmed on 35 of 83 real files).
    Session identity now resolves once, up front, from the file itself
    (`session.source_path`) rather than lazily from whichever `session_meta`
    a given harvest batch happens to encounter first — the lazy version
    worked within a single batch but reintroduced the bug across an
    incremental resume, which is the only way this collector is ever
    actually run.
  - `INSERT OR IGNORE`, used to dedupe on the natural-key constraint, silently
    swallows *every* constraint violation on that statement, not just the
    intended duplicate — so a record missing a required field (`timestamp`)
    would previously vanish with no error and no count, rather than being
    reported like any other malformed line. Required fields are now checked
    explicitly before the insert is attempted.
- **Corrected an `is_subagent` design decision within the same implementation
  session that made it.** Planning for the Claude collector concluded
  `isSidechain` was dead in current transcripts — a scan of every file found
  by a non-recursive directory glob showed zero `isSidechain: true` records,
  including in sessions known to have used subagents. Shipped as
  `is_subagent = 0` always for Claude, documented as a finding. Harvesting the
  real corpus mid-implementation surfaced the actual cause: current Claude
  Code writes background/queued subagent transcripts to a nested
  `subagents/<parent-session-uuid>/agent-<agent-id>.jsonl` path that a
  non-recursive glob never reaches. Correctly scanned, `isSidechain: true`
  appears on 19,139 real records across 362 of 714 files (over half the
  corpus) — with complete, real `usage` blocks. `token-report`'s original
  assumption was right; `is_subagent` is now read per record from
  `isSidechain`, not derived from a session-level lookup the way Codex's is
  (a subagent file shares its parent's own `sessionId` rather than declaring
  a distinct one, so there is no separate child identity to look up).

## [0.7.0] — 2026-08-08

### Added

- **Usage store bootstrap.** `flow setup machine` and `flow update` now create
  and migrate `~/.flow/usage.db`, a SQLite store for harvested harness usage
  data (Claude Code and Codex session transcripts). Two layers: raw turn
  records in each harness's own semantics, and a normalized layer recomputable
  from raw at any time — the split exists because Codex's `cached_input_tokens`
  is a subset of `input_tokens` while Claude's cache buckets are disjoint and
  additive, so a single shared column would make cross-harness totals quietly
  wrong. `flow doctor` reports store state (absent / stale / empty / ok)
  read-only; it never creates or repairs. No collector ships yet — nothing
  writes turns.
- **Capability seed data** at `data/harness_capabilities.json`, describing what
  each harness's transcripts can report (context window, cache TTL semantics,
  session lineage, etc.). Lives at the top level rather than under
  `scaffolds/default/` because `setup_project()` copies everything under
  `scaffolds/default/` into every project's `.flow/` overlay, which would leak
  machine-level seed data into every repo.

### Changed

- **`cli/flow.py` split into eight modules.** It was 1,876 lines holding every
  CLI concern; it is now 224 — argparse declaration and dispatch only.
  `paths.py`, `flowtoml.py`, `fsutil.py`, `render.py`, `sync.py`, `setup.py`,
  `lifecycle.py`, `diagnostics.py` hold everything else, in an acyclic
  dependency graph. See `docs/file-structure.md` for what each module owns.
  Verified as a pure move: of the 67 functions on the prior `flow.py`, 63
  remain code-identical (one intentional deletion of dead code and two
  intentional bug fixes below account for the rest).
- **Release staging validation now resolves imports instead of guessing what
  they are.** The prior check (`CLI_REQUIRED_SIBLINGS`) was a hand-maintained
  tuple naming one required sibling file while `flow.py` actually needed six —
  itself the same forward-compatibility gap the [0.6.1] roster blacklist fixed
  for release *contents*, recurring for release *validation*. The replacement
  reads required sibling names directly out of the staged `flow.py`'s imports,
  transitively. An earlier version of this fix classified every non-stdlib
  import as a required flow module, which would have made any future
  third-party dependency unrecoverable from an older client (the rejecting
  code being the installed code); it was corrected before release to instead
  ask whether each import *resolves* — against the staged tree or the running
  environment — which needs no forecast of what a later release might add.
- **`quality-reviewer` and `security-reviewer` repinned `sonnet` → `opus`.**
  Both sit where a wrong call cascades downstream, matching the rest of the
  agent set.
- **`flow-archive` records framework capability gaps.** A new required output
  section captures what the *framework* was missing during a run — a step done
  by hand that a command should own, a missing standard, an agent role that
  would have fit — distinct from what the work itself left undone. "none
  observed" is required rather than optional, since an omitted section is
  indistinguishable from one never considered.
- **`flow-implement`'s parallel investigation now writes to
  `.flow/runs/<work-id>/research/`** instead of the working directory, and the
  orchestrator is directed to collect the returned file paths rather than
  synthesize from inline summaries alone, which discards the detail those
  files exist to hold.

### Fixed

- **Current Codex standalone-skill discovery.** Codex adapters now generate
  required `name` and `description` frontmatter under `.agents/skills/` while
  retaining `.codex/flow.managed.toml` for Flow's ownership tracking. Existing
  manifests that declare the former `.codex/skills` path migrate on their next
  sync; only previously managed legacy files are removed. Claude generation is
  unchanged.
- **Installer Python selection hardened.** `install-flow.sh` now searches a
  broader, deduplicated set of Python candidates (`FLOW_PYTHON`,
  `FLOW_PYTHON_CANDIDATES`, versioned `python3.1x` on `PATH`, then Homebrew
  prefixes) and rejects anything below the 3.10 floor with a clear error
  instead of failing opaquely later.
- **`desired_claude_outputs` / `desired_codex_outputs` no longer discard the
  managed manifest's own first build.** Each function built the manifest,
  appended the manifest's own entry to the entry list, then rebuilt and
  discarded the first result — harmless (the builder is a pure string
  function) but wasteful. The entry is now appended before the single build.
- **Removed `render_skill` (`cli/render.py`).** Dead code with no callers
  anywhere in the repo, predating this release.

### Why this is 0.7.0 (minor)

Two of the changes above alter runtime-visible behavior for existing users: the
usage store adds a new artifact and a new `doctor` line, and the `flow-archive`
/ `flow-implement` changes alter how agents engage at runtime per this file's
own preamble on `scaffolds/default/` changes. The module split and the staging
fix are internal and would be patch-level on their own.

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
