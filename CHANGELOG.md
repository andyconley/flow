# Changelog

All notable changes to flow are generated from Conventional Commits. Longer design context belongs in the documentation changed by the release.

## [0.13.2](https://github.com/andyconley/flow/compare/v0.13.1...v0.13.2) (2026-08-19)

### Bug Fixes

* **doctor:** stop reporting flow's own home as a project overlay ([39149c8](https://github.com/andyconley/flow/commit/39149c8587081db3f02c05a4ad7516cd290ee063))

## [0.13.1](https://github.com/andyconley/flow/compare/v0.13.0...v0.13.1) (2026-08-19)

### Bug Fixes

* **release:** pin conventionalcommits preset to a renderable major ([15344d8](https://github.com/andyconley/flow/commit/15344d80c27ae122a03362a32b1334195d49793a))

### Documentation

* **changelog:** restore the notes 0.12.0 and 0.13.0 never got ([dc02abe](https://github.com/andyconley/flow/commit/dc02abe32aafebdfe0d69bffc3b3ef9fd2479543))

### Continuous Integration

* **release:** fail the build when a release describes nothing ([c499a22](https://github.com/andyconley/flow/commit/c499a2220c7fb2349af56ded1dbc0f8135a0f1c3))

## [0.13.0](https://github.com/andyconley/flow/compare/v0.12.0...v0.13.0) (2026-08-19)

### Features

* **cli:** wire flow plugin-usage snapshot and show ([6b5c116](https://github.com/andyconley/flow/commit/6b5c116711ad6cfd3cd5de55e0ceeb7a8e9418b9))
* **doctor:** render the usage section ([024dbe3](https://github.com/andyconley/flow/commit/024dbe3c100af670ef90c6e79ec20921fc58ef3c))
* **harvest:** sample usage counters as a backstop ([d2c3d60](https://github.com/andyconley/flow/commit/d2c3d60984bcce8ac2c036a7ee05a36025fd6abf))
* **hooks:** observe usage counters on SessionStart ([74c0a49](https://github.com/andyconley/flow/commit/74c0a49d4c65c6fe60d4f1eaea2acd26eb410cfc))
* **plugin-usage:** add reader for Claude's on-disk configuration ([918505f](https://github.com/andyconley/flow/commit/918505f0bc6d54aa2f659dc434cd8017ec25e07e))
* **plugin-usage:** add usage history capture and the doctor read model ([3ec1b1f](https://github.com/andyconley/flow/commit/3ec1b1fa47510e10f336dec7167d664d1bff042e))
* **store:** add migration 6 for plugin and skill usage observations ([a3ea411](https://github.com/andyconley/flow/commit/a3ea411f6c19347fbd09b8facfed871ae1bec8ae))
* **store:** declare plugin_usage_counters capability ([097b15a](https://github.com/andyconley/flow/commit/097b15ad2febe489ddcf60d12c74232ed87fd407))

### Bug Fixes

* **plugin-usage:** close review findings on misleading output ([ae136da](https://github.com/andyconley/flow/commit/ae136da402bcb339b017d50db8d9787f1f1f0318))

### Documentation

* **plugin-usage:** reference sections, design record, and README note ([bbe0e96](https://github.com/andyconley/flow/commit/bbe0e963dc1cb33b0124256b6b42ccf5d35938d2))

### Tests

* **plugin-usage:** prove the write path, read model, and rendering ([8617eb9](https://github.com/andyconley/flow/commit/8617eb9f4bcddf45ca1ff2d9bb3dda2f48c0ea2f))

## [0.12.0](https://github.com/andyconley/flow/compare/v0.11.1...v0.12.0) (2026-08-17)

### Features

* **baseline:** estimate the always-on token floor from turn-1 cache reads ([498113d](https://github.com/andyconley/flow/commit/498113d94c9599f2501255dd4df79e7b4fd3ef4c))
* **cost:** add flow cost baseline ([a94ba73](https://github.com/andyconley/flow/commit/a94ba73d6bc7e8ccf284f797964b12f8e709e923))

### Bug Fixes

* **baseline:** detect changes within a series, not across grouped rows ([7a4be49](https://github.com/andyconley/flow/commit/7a4be49d127a7cdb6c38d3df34c960f5147046f6))

### Documentation

* record the cost baseline design and reference ([90e8d8d](https://github.com/andyconley/flow/commit/90e8d8d6af0e3326055c60dc932929787b057fc1))

### Tests

* **baseline:** cover the population rules and the detection floor ([b1ef862](https://github.com/andyconley/flow/commit/b1ef862695ffb5b821e04d54df42bac2cca9b729))

### Continuous Integration

* use current release workflow actions [skip ci] ([3329ded](https://github.com/andyconley/flow/commit/3329ded3975908be3c46bae1b4266b1c6849dfca))

### Maintenance

* **data:** declare compact_boundary capability per harness ([fabfd1f](https://github.com/andyconley/flow/commit/fabfd1f78a59a1bc3b96c1782ea1eebf54af1672))
* **release:** clean changelog carryover [skip ci] ([6209d80](https://github.com/andyconley/flow/commit/6209d80e8a1a1544c11f37051feda50635dfe9d0))
* **release:** fix changelog commit link [skip ci] ([74dd850](https://github.com/andyconley/flow/commit/74dd85063fb29defc8413ac3edbd9b940ad2c93f))

## [0.11.1](https://github.com/andyconley/flow/compare/v0.11.0...v0.11.1) (2026-08-16)

### Documentation

- clarify release-impacting documentation ([cc16fcf](https://github.com/andyconley/flow/commit/cc16fcf125016d475b2b1d96129016dbde359b3d))

## [0.11.0] — 2026-08-16

The definition and overlay-refresh release. Flow now has a real front door for
early scope work, and project refresh no longer assumes every repo wants a
project-local copy of the whole framework.

The important product change is `/flow-define`: discovery, research,
adversarial review, and approved requirements now have a first-class stage
before `/flow-solution` or `/flow-plan`. That gives product, architecture, and
business-analysis roles a place to turn an idea or capability into agreed
requirements before implementation planning starts.

The operational fix is narrower but just as important. `flow refresh project`
used to copy every missing file from the framework scaffold. In repos that
intentionally rely on the user-level install for commands and agents, that
backfilled inert duplicate framework files and created future drift. Refresh is
now conservative by default: it adds missing overlay core files and registered
local sources, reports same-name files whose content differs, and leaves those
files alone unless the user chooses an interactive update. The old broad
backfill remains available through `flow refresh project --all`.

### Added

- **`/flow-define`** — a definition stage for early feature or architectural
  capability work. It covers discovery, research, adversarial questioning, and
  approved requirements before planning or solutioning.
- **Definition artifacts and guidance** — templates and standards for
  requirements, research notes, adversarial review, and definition-stage
  evidence.
- **Community health files** — MIT license metadata, contribution guidance,
  security policy, issue templates, and pull request template.

### Changed

- **`flow refresh project` is conservative by default.** It repairs overlay
  core files and registered local sources without importing every framework
  command, agent, standard, template, and project starter file.
- **`flow refresh project --interactive` reports and prompts on update
  candidates.** Existing same-name files whose content differs from the
  framework are not overwritten in normal runs.
- **`flow refresh project --all` keeps the old broad backfill path** for repos
  that intentionally want a full project-local framework scaffold.
- **`flow bootstrap` treats framework directories as optional.** Missing
  `commands/`, `agents/`, `standards/`, `project/`, and `templates/` no longer
  fail bootstrap when the overlay core is present.
- **README, CLI reference, help, and backlog docs now match the current
  install/update and overlay model.**

### Fixed

- **Usage-store setup recovers from partial migration state** instead of
  leaving a develop install unable to repair the local usage database.
- **Project refresh no longer creates duplicate inert framework content** in
  overlays whose manifests intentionally declare no project-local commands or
  agents.

## [0.10.0] — 2026-08-15

The measurement release. `flow cost` could say which sessions need attention
right now. It could not say whether anything you changed was working, and three
of its inputs were lossy in ways no surface disclosed.

The largest of those was not a rounding error. A streamed Claude response is
written as several transcript lines sharing one request id, and only the last
carries the final `output_tokens`; the collector kept the first. Measured
against the Anthropic console, that recovered 67% of output — and the intuitive
fix, summing the group, triple-counts one request's inputs and overshoots by
51%. The rule that is actually right is asymmetric: inputs from any line,
output from the maximum.

Two of the defects behind this release were invisible by construction rather
than merely unnoticed. A corrected raw payload did not mark its normalized row
stale, so the fix reached the store and stopped one layer short of every view
that reads it — raw held 31.90M output tokens against 28.13M normalized, both
tables internally consistent, nothing reporting the gap. And the Codex capacity
gauge rendered a percentage without the expiry it had stored all along, so a
six-day-old reading described the present with a straight face. Both are the
same shape: a number that is locally true and globally misleading, with no
mechanism that would ever say so.

So the theme is disclosure. `trend` shows whether efficiency is moving.
Context windows resolve at read time and say which of four sources produced
each one, with an honest blank where none did. Coverage gaps are labelled
instead of truncated. Compactions are split by trigger and never summed,
because a deliberate `/compact` and hitting the ceiling are opposite signals.
An expired gauge is absent rather than dimmed.

Recovering the capture fixes on transcripts already on disk takes one
`flow harvest claude --rescan` followed by `flow normalize`. On the corpus this
was built against that recovered 14.4% of output tokens and 29 compaction
events. Transcripts already pruned from disk keep their partial counts — 1.0%
of stored turns, and no re-read can reach them.

### Added

- **`flow cost trend`** — efficiency per time bucket, the view that answers "is
  my session hygiene actually working." Every other `cost` view reports a
  level; this reports the shape of the levels over time. One row per bucket
  *and* harness (`--bucket day|week`, `--harness claude|codex`): main-agent
  turns, distinct sessions, context per turn, input:output, weighted tokens per
  1,000 output, subagent share, and compaction events split by trigger with the
  median context at manual cuts.

  `wt/1k out` is the headline. It collapses the input classes by billing
  multiplier and divides by output, which is what makes it an efficiency
  number — raw daily burn conflates working less with working leaner. The
  multipliers live in `data/token_weights.json`, so a pricing change is a data
  edit rather than a release.

  Weighted columns are blank for Codex, never zero. The weights are Anthropic
  cache multipliers, Codex reports no cache writes at all, and its cache-read
  semantics differ — the same arithmetic would not mean the same thing.

  Coverage is labelled rather than silently truncated: a window reaching before
  a harness's earliest harvested turn says so, because absent buckets and empty
  buckets are different facts and hiding the difference turns a coverage gap
  into a false trend.

  Buckets follow the **local** calendar. Stored timestamps are UTC and every
  window comparison stays UTC, but a bucket is a label on a human day —
  bucketing by UTC split an evening across two rows and moved 7% of a week's
  turns off the day they happened. Weeks are keyed by their Monday's date
  rather than a week number, since `%W` counts weeks within a calendar year and
  would split a week spanning New Year into two partial buckets.

- **Context windows resolve at read time**, from `data/model_context_windows.json`
  and from the transcript. `turn_norm.context_window` is NULL for every Claude
  turn and deliberately stays that way — that column means "the harness
  reported this," and filling it with a lookup would destroy the
  measured-versus-inferred distinction the `~` marker depends on.

  Best source first: the statusline's exact record; then `preTokens` at an
  **auto** compaction in that same session, which fires at the ceiling and so
  observes what the session actually held; then the model table, marked `~`;
  then nothing. The compaction signal is scoped to its own session and never
  generalised to the model — every model that has auto-compacted also runs in
  200K sessions constantly, so a model-wide rule would divide all of those
  percentages by five.

  A model absent from the table now reports `?` and no recommendation instead
  of assuming 200K. An honest blank beats a confident wrong number in a tool
  whose purpose is measurement, and it is the signal that the file needs an
  entry.

- **`flow cost active` shows subagent share** per session. `ctx` and `carry`
  measure the main thread only, so work moved into subagents leaves both
  looking better without costing less. Subagent share moved 4.8% → 12.9% over a
  window in which main-agent context fell 41%; a metric that improves when work
  is *moved* eventually gets optimised the wrong way, so the two are shown
  together.

- **`flow harvest claude --rescan`, with `--since`, `--session`, and
  `--dry-run`.** A plain harvest only reads what is new, so a collector
  improvement never reaches transcripts already on disk. `--rescan` re-reads
  them. It supersedes `--backfill`, whose name described only the first thing
  it ever did; `--backfill` still works and is hidden from help.

  Rescanning the whole corpus re-reads every recorded transcript, so the
  filters exist to rehearse it on a slice first. A filter resolves to whole
  sessions rather than to literal file matches — the watermark is per file but
  the derived title state is per session, and replaying only some of a
  session's files while resetting all of its state leaves the un-replayed
  files' titles unrecoverable.

  Follow a rescan with `flow normalize`; the command says so.

- **`turn_norm.cache_write_1h_tokens` / `cache_write_5m_tokens`** (schema v5).
  Claude's `usage.cache_creation` carries the cache-TTL breakdown, which sums
  exactly to `cache_creation_input_tokens` across 20,587 real turns. The
  halves bill 60% apart — 2.0x base input for 1h, 1.25x for 5m — so one
  collapsed column makes the write component of any cost estimate off by up to
  that much, and writes are about a quarter of the bill. `cache_write_tokens`
  stays the total; no consumer changes. Codex leaves both NULL. No re-harvest:
  the fields were always in the raw payload, just unread.

  One real turn out of 29,592 violates the sum, and it is the harness's own
  inconsistency rather than an extraction bug: on a fallback turn (two entries
  in `usage.iterations`, a model switch mid-turn) the top-level
  `cache_creation_input_tokens` reflects the second iteration while
  `cache_creation` reflects the first.

- **`compact_boundary` events are captured** into `agent_activity_raw`, beside
  Codex's `sub_agent_activity`. They are Claude's only explicit record of
  context management and were dropped entirely. The payload is stored verbatim
  because `compactMetadata.trigger` separates a deliberate `/compact` from
  hitting the ceiling — opposite signals about a session's health that a
  single tally would destroy. Recovered 29 events from the local corpus
  (18 manual, 11 auto) on the first rescan.

### Fixed

- **The Codex capacity gauge had no expiry.** `flow cost summary --days 7`
  reported `10080m window 96.0%` on 2026-08-15 from a reading taken 2026-08-09
  that expired 97 minutes after the run — still literally true when taken,
  wholly misleading when shown. The capacity window is 10,080 minutes, exactly
  the length of the default summary window, so a reading anywhere in range can
  describe a period with almost no overlap with the present.

  `resets_at` was stored all along and never rendered. The gauge now shows it
  beside `as of`, and drops each field once its own reset time passes — an
  expired gauge is absent, not dimmed. Primary and secondary expire
  independently, since neither name reliably means "the short window." A
  reading sampled more than halfway through its own window is still shown, with
  a note.

  `scaffolds/default/commands/flow-plan.md` told the agent to report that line
  "verbatim — no interpretation." For a field carrying its own expiry, verbatim
  is the wrong contract, and that instruction is what produced the misleading
  report. It now requires the expiry alongside, and silence when the line is
  absent.

- **Claude turns stored a streamed response's *partial* output token count.**
  A single API response is written as several assistant JSONL lines sharing
  one `requestId`. Every input field repeats byte-identically; `output_tokens`
  does not — it grows as the response streams and is final only on the line
  carrying `stop_reason`. A real group reads [4, 4, 4, 4, 4, 487].

  `INSERT OR IGNORE` kept the first line, so that turn was stored as 4 output
  tokens. Measured against the Anthropic console for the same account and
  period, first-wins recovered 67% of output. Replaced with an upsert guarded
  on the output count: inputs from any line, output from the maximum. Summing
  the group is the intuitive fix and is wrong — it triple-counts one request's
  inputs and overshoots output by 51%.

  `max` over `last` (they differ by 2 tokens across the whole corpus) because
  it is order-independent, so replaying a file cannot corrupt a row. `ts` and
  `turn_seq` keep the first line's values, so a response that finishes after
  midnight does not migrate across a day boundary on re-harvest.

  Recovering this on already-harvested transcripts needs one
  `flow harvest claude --rescan` followed by `flow normalize`. On the corpus
  this was built against that recovered 14.8% of output tokens. Transcripts
  already pruned from disk cannot be reached — 298 of 29,437 stored turns
  (1.0%) keep their partial counts permanently.

- **A corrected turn did not reach the normalized layer.** `normalize_all`
  selects stale rows by `norm_version` alone, and nothing marked a `turn_norm`
  row stale when its `turn_raw` payload changed underneath it — until the
  upsert existed, a payload never could. Since `flow cost active` harvests and
  then normalizes, a turn stored mid-stream got stamped current and kept its
  partial count forever, with both tables self-consistent and nothing
  reporting it. Found on the real corpus, where raw held 31.90M output tokens
  against 28.13M normalized.

- **`--dry-run` wrote.** It ran `ensure_store` before the dry-run branch, so a
  rehearsal applied pending schema migrations and re-seeded capabilities while
  printing "nothing written". It now returns first and opens the store
  read-only. It was also gated on `~/.claude/projects/` existing, so it
  reported "no sessions found" with a full store to describe.

- **`docs/cli-reference.md` covers all twelve subcommands.** It documented
  eight and was two releases behind: the entire v0.8.0 usage-tracking surface
  (`harvest`, `normalize`, the five `cost` views) and the v0.9.0 overlay
  surface were absent, as was `flow help`. Its Overview also claimed flow
  manages three things and named neither. A reader learning the CLI from that
  file would have concluded `flow cost` did not exist.

  Also documents what `--help` cannot say: the harvest → normalize → cost
  ordering and which views run it for you (`active` and `verdict` do, and only
  for Claude — Codex totals go stale until `flow harvest codex` is run by
  hand); the actual `/clear`-or-`/compact` thresholds; the verdict-file and
  throttle-marker paths, which are what you inspect when an advisory
  misbehaves; and five new failure modes, including the one all three hook
  entry points share — silence by design looks exactly like breakage, so it
  gets a diagnostic order starting at `~/.flow/logs/hook-errors.log`.

- **The CLI reference is now checked against the CLI.** A test asserts every
  documented command resolves, every documented flag is accepted, every
  documented default matches `--help`, every shipped subcommand appears in
  some section, and the output literals the doc quotes as searchable symptoms
  are what the CLI actually prints. It also guards its own parse, so a regex
  that stops matching fails loudly instead of iterating over nothing.

  In `tests/` rather than `scripts/` deliberately: it runs without anyone
  remembering to run it, which is why the doc drifted, and `tests/` is
  excluded from the release roster so a dev-only check does not ship.

## [0.9.0] — 2026-08-11

The overlay release. `~/.flow/user/` was the one authored layer with nothing
behind it — hand-written content in a machine-local directory, no history, no
backup. It gets a git home, a status query, and an advisory that notices when a
session walks away without committing what it just edited.

The convention that advisory enforces was already written down, and that turned
out to be the problem. `FRAMEWORK.md` says the agent editing overlay content
commits it in the same turn; a compaction or a fresh session quietly stopped
honoring it, and nobody found out until the next `doctor` run.

### Added

- **`flow overlay`** — `status` reports the user overlay's version-control
  state on demand; `check --hook` is the engine behind a new advisory that
  catches sessions drifting from the commit-in-the-same-turn convention.
  That convention previously lived only in `FRAMEWORK.md` and auto-memory,
  so a compaction or a fresh session quietly went back to piling up
  uncommitted work, discovered whenever someone happened to run `doctor`.

  `flow-overlay-reminder.sh` registers on **PostToolUse** (the edit, while
  it is fresh) and **UserPromptSubmit** (whatever is still outstanding at
  the next turn boundary), on both runtimes. Not Stop, which is the
  intuitive choice and the wrong one: Stop's stdout reaches the transcript
  rather than the model, which is exactly why `flow-token-verdict.sh` writes
  a file there instead. The nudge arrives one turn later than Stop would
  have, but somewhere the agent can act on it.

  Silent unless the overlay is a repository with something outstanding, so
  it costs nothing for anyone who has not opted in. The prompt-boundary
  advisory re-fires as soon as the outstanding set changes rather than
  waiting out its window, so work piling up behind a throttle does not go
  unmentioned; the edit-time one stays quiet across a burst, since a
  ten-file change should produce one line rather than ten.

- **`cli/hookio.py`** — defensive stdin reading, throttle markers, and the
  swallowed-error breadcrumb log, shared by every runtime hook. Extracted
  from `cost.py` rather than copied, on the reasoning that moved
  `jsonl_watermark` and `session_lookup` out of the collectors. Depends on
  nothing but `paths`, because `UserPromptSubmit` hooks run on every prompt
  and importing the usage store there would put a SQLite import on that path
  for hooks that never touch it.

- **`flow setup user --overlay-repo <url>`** — gives `~/.flow/user/` a git
  home. The overlay is the one authored layer with no repo behind it: the
  framework scaffold lives in this repo, project overlays live in theirs,
  and the user overlay was hand-authored content in a machine-local
  directory with no history and no backup. Three cases, none of which
  discard content: already a repo, report and leave alone (re-pointing a
  remote is deliberate, not a setup side effect); absent or empty, clone
  (the new-machine path); has content but no `.git`, init in place and add
  the remote. A `.gitignore` covering `.env`, `keys/`, `*.pem`, and
  `*.local.*` ships into a fresh overlay so a future credential-bearing
  file can't land by accident. Setup never commits — `FRAMEWORK.md` records
  the convention instead: the agent that edits overlay content commits it
  in the same turn, because the person who owns that content is not the one
  editing it.
- **`flow doctor` reports the overlay's version-control state** — untracked
  (naming the fix), or clean / N uncommitted / N unpushed with the branch.
  It also now reports overlay hooks alongside commands and agents, which it
  had never listed. New module `cli/overlay.py` holds the status query, kept
  out of `diagnostics.py` so `doctor` keeps holding presentation rather than
  git plumbing; a few bounded local git calls, skipped entirely when there is
  no overlay, and it never writes. A failed git call reports `unreadable (git
  error)` rather than a synthesized clean-looking status.

### Changed

- **The overlay advisory hook costs one fewer subprocess per prompt.** It
  reads `git status --porcelain=v2 --branch`, whose header names the upstream
  ref directly, so `config --get remote.origin.url` — ~45ms of process spawn
  on every prompt — is no longer needed to answer "is anything unpushed".
  `overlay_vcs_status` grew a `quick` flag for this; `doctor` and `setup`
  still take the full status and behave exactly as before.

  The hook gives up one distinction in exchange: a repo with a remote
  configured but no upstream set now reads to it the same as a repo with no
  remote at all. Merging those two means the wording has to hold for both, so
  it claims only what the field establishes — *no upstream branch, so nothing
  here is tracked against a remote*. It deliberately does not say the content
  is only on this machine: `git push origin main` without `-u` leaves the
  content on the remote and the branch untracked, and that is the state
  `setup`'s init-in-place path produces. `doctor` still separates the two.

  In that standing-only state the advisory also stops telling the session to
  commit and push. There is nothing dirty and nothing ahead, so there were no
  changes to refer to, and the fix — setting an upstream — pushes the whole
  branch, which is exactly what a session that did not author the repo must
  not run. It now names the condition and leaves it to the repo's owner.

  Porcelain v2 also changes how a rename appears in the dirty list: v1
  reported `old -> new`, v2 reports the new path alone.

## [0.8.0] — 2026-08-10

The usage-tracking release. flow measures what agent sessions cost. It says
when a session is carrying dead weight, in the places you can act on it: the
statusline, the prompt, the workflow commands. It reads transcripts already
on disk. No API calls.

### Added

- **`flow harvest codex` and `flow harvest claude`** — read each harness's
  session transcripts into `~/.flow/usage.db`. Each file resumes from a byte
  watermark. Safe to run repeatedly or on a schedule.

  Both collectors ran against this machine's full corpus during development.
  That corpus contradicted four assumptions the fixtures had passed. Codex
  writes a second copy of the parent's `session_meta` into subagent files.
  One Codex turn spans several token counts. Claude subagent transcripts sit
  in nested `subagents/` directories and carry the parent's session id.
  `INSERT OR IGNORE` swallows every constraint violation, not just duplicate
  keys.

  `flow harvest claude --backfill` replays recorded files, so old sessions
  pick up titles, working directories, and title provenance.

- **`flow normalize`** — projects raw turns into one token convention across
  harnesses. The harnesses disagree about their own numbers. Codex reports
  cached input as a subset of input tokens. Claude's cache buckets are
  disjoint and additive. One shared column would make cross-harness totals
  quietly wrong. So raw records keep each harness's meaning, and the
  normalized layer can be recomputed when a rule changes.

  Schema v4 adds title provenance and a per-session timestamp high-water
  mark. Title records carry no timestamps of their own; the high-water mark
  is what resolves repeated auto-titles to the newest one.

- **`flow cost`** — reads it back out.
  - `summary` — totals by harness and model, plus the most recent Codex
    capacity reading on its own gauge line. A snapshot doesn't sum, so it
    stays out of the totals. It is labeled by the window size actually
    stored: `primary` and `secondary` don't reliably mean what they sound
    like.
  - `sessions` — per-session totals, most recently active first. Capped at
    the 20 most recent. `--limit 0` shows everything.
  - `active` — context percentage, carry above session start, idle time, and
    a `/clear`-or-`/compact` recommendation per live session. Harvests and
    normalizes before answering, so the numbers are current. Replaces
    `token-report --active`, and produced identical results running side by
    side against it on live sessions.
  - `verdict` and `warn` — the engines behind the hooks below. Callable by
    hand for debugging.

- **Post-turn verdict and pre-execution warning hooks, both runtimes.** After
  each turn, a Stop hook judges whether the session should `/clear` or
  `/compact`, then writes the verdict file the Claude statusline already
  reads. Before the next prompt, a UserPromptSubmit hook injects one advisory
  line once carry passes 100K, and again after another 50K of growth.

  Both hooks stay advisory. They print nothing else. They discard their own
  errors, leaving a breadcrumb in `~/.flow/logs/hook-errors.log`. They always
  exit 0, because exit code 2 blocks a Stop or erases a prompt on both
  runtimes. `~/bin/token-report` is retired.

- **`[[codex.hooks]]`** — Codex hook management, at parity with Claude's.
  Manifest entries deploy scripts to `.codex/hooks/` and merge handlers into
  `.codex/hooks.json` under the preserve-unmanaged contract. `config.toml` is
  never touched. Hook scripts must be named `flow-*`; sync rejects anything
  else, because the unmanaged-content protection identifies flow's handlers
  by that marker. The user overlay can add or override hooks for either
  runtime, with scripts from `~/.flow/user/hooks/`.

- **Usage advisory in the workflow commands.** `flow-boot` reports Codex
  capacity and any session the tools flag. `flow-status` reports the current
  session's cost. `flow-plan` and `flow-solution` note cost posture next to
  their recommendations. All of it is informational, stated inline in every
  edit: no advisory line blocks a phase or changes a default, and absent data
  means silence.

- **Agent model routing.** `flow.toml` model tiers map role agents to runtime
  models per target. Generated skills carry a routing table, so commands
  dispatch each role to the right model. `flow doctor` reports the active
  policy and a manual smoke test.

### Changed

- `flow harvest claude --backfill-titles` is now `--backfill`. The same
  replay repairs `cwd` and title provenance, so the old name was too narrow.
- `flow cost sessions` caps at the 20 most recent sessions by default.

### Fixed

- Overlay version-control state is asked of git rather than inferred from a
  `.git` directory on disk. `.git` exists only at a work tree's root, so the
  filesystem test called every committed subdirectory and every symlinked
  overlay untracked — the arrangement that results from keeping the overlay
  inside a larger dotfiles repository. Three further corrections came with
  it: a missing git binary is no longer reported as an untracked overlay
  (with `--overlay-repo` offered as the fix for a broken machine); a
  directory that is inside a repository but gitignored is no longer reported
  as backed up, since `rev-parse` succeeds there while nothing ever gets
  committed; and the unreadable-git case no longer claims `tracked`, because
  with no git to ask, membership is unknown. `doctor` now names the
  repository when the overlay is not its own root.

- Generated skills' "Edit `...`" hint points at a file that exists, for every
  origin and sync mode. User-overlay commands point at `~/.flow/user/...`.
  Framework commands installed at user level point at the scaffold. Project
  mode keeps the `.flow/...` form. The old hint sent every non-project edit
  to a path that wasn't there.
- Dropping a merge-mode file (`.claude/settings.json`, `.codex/hooks.json`)
  from a manifest no longer deletes it. Those files hold your content
  alongside flow's. They are now unmanaged in place.

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

[0.11.0]: https://github.com/andyconley/flow/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/andyconley/flow/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/andyconley/flow/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/andyconley/flow/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/andyconley/flow/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/andyconley/flow/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/andyconley/flow/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/andyconley/flow/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/andyconley/flow/compare/v0.4.5...v0.5.0
[0.4.5]: https://github.com/andyconley/flow/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/andyconley/flow/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/andyconley/flow/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/andyconley/flow/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/andyconley/flow/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/andyconley/flow/releases/tag/v0.4.0
