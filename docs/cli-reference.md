# flow CLI Reference

## Overview

`flow` manages five things:

- machine-local install support
- project-local `.flow` scaffolding
- runtime adapter generation and drift detection
- token usage: reading both harnesses' local transcripts into a store, and reading it back
- version control for the user overlay at `~/.flow/user/`

Three **hook entry points** exist only to be called by generated hooks — `flow cost verdict --hook`, `flow cost warn --hook`, and `flow overlay check --hook`. They read hook JSON on stdin and are documented here for anyone reading a `settings.json` entry and wondering what it invokes, not because there is a reason to type them. (`flow cost verdict` also has an interactive `--transcript` mode, which is worth typing.)

The usage-tracking commands form a pipeline, and the order matters: **`harvest` writes raw records → `normalize` projects them into one token convention → `cost` reads the normalized layer.** `flow cost active` and `flow cost verdict` run the needed harvest/normalize work for the current surface; `flow cost summary`, `flow cost sessions`, `flow cost trend`, and `flow cost baseline` stay read-only and label freshness so stale data does not look current.

## Command Reference

### `flow setup machine`

Prepare machine-local support under `~/.flow`.

Creates:

- `~/.flow/config.toml`
- `~/.flow/hooks/`
- `~/.flow/user/`
- `~/.flow/logs/`

Use this when setting up a new machine or repairing a missing local install surface.

### `flow setup project`

Scaffold `repo/.flow` into the current repository.

Behavior:

- creates exactly four paths: `flow.toml`, `PROJECT.md`, `memory/STATE.md`, and `runs/.gitkeep`
- does not overwrite files that already exist
- copies no commands, agents, standards, templates, or `FRAMEWORK.md`. Those are framework capability, served by the user-level install; copying them into a repo produced a fork that never updated. A project set up before this change can be reconciled with `flow project migrate`.

Use this when bootstrapping a repo for the first time.

### `flow setup user`

Install flow at the **user level** so it is active in every supported runtime session regardless of cwd.

Behavior:

- runs `flow sync claude --user` and `flow sync codex --user` in sequence
- generates `~/.claude/skills/flow-*/`, `~/.claude/agents/*.md`, `~/.claude/hooks/flow-*.sh`
- generates `~/.agents/skills/flow-*/`, `~/.codex/agents/*.toml`, `~/.codex/hooks/flow-*.sh`
- merges flow hook entries into `~/.claude/settings.json` (preserves unmanaged settings)
- writes `~/.claude/flow.managed.toml`, `~/.codex/hooks.json`, and `~/.codex/flow.managed.toml` for hook registration and drift tracking

Use this once per machine, then again whenever the framework scaffold changes and you want the user-level surface to follow.

### `flow refresh project`

**Retired.** Exits 1 and points at the commands that took over.

It repaired a missing manifest and missing core files, and restored manifest-declared sources from the scaffold. The first two are things `flow setup project` already does idempotently; the third is fork restoration in miniature, and is what `flow project migrate` exists to undo. A project overlay no longer holds framework files, so there is nothing left for it to refresh.

| what it used to do | what to run |
|---|---|
| missing `flow.toml` or core files | `flow setup project` |
| framework copies still present | `flow project audit`, then `flow project migrate` |

**One capability has no successor.** Updating an *existing* `PROJECT.md` or `memory/STATE.md` from the framework template is gone — `copy_if_missing` never touches a file that is there, and nothing else offers the update. Those files are the project's own content from the moment it is initialized, so edit them directly. The retirement message says this rather than leaving it to be discovered.

The refusal fires before any filesystem check, including whether `.flow` exists. Someone typing a retired command needs to hear that it is retired, not a setup error about a directory the command would no longer have touched.

### `flow bootstrap`

Validate that the minimum `repo/.flow` structure exists.

Checks for:

- `flow.toml`
- `PROJECT.md`
- `memory/`

It reports absent `commands/`, `agents/`, `standards/`, `project/`, and `templates/` directories as optional. The user-level install provides framework commands and agents unless the project overlay registers local replacements.

Use this after scaffold or when diagnosing a broken repo state.

### `flow help`

Print the framework orientation: workflow phases, slash commands, CLI commands, agents, and architecture.

Same content as the `/flow-help` slash command. Use this at a shell when you are not inside a Claude session.

### `flow run list`

List workflow runs under the current repo's `.flow/runs/` directory.

Flags:

- `--all` — include archived runs
- `--json` — emit JSON

Runs with `run.json` are C-lite runs. Existing artifact folders without `run.json` are reported as `legacy/inferred`; reading them does not create state.

### `flow run status <work-id>`

Show one run's current state.

Flags:

- `--json` — emit JSON

For C-lite runs, this reads `.flow/runs/<work-id>/run.json`. For legacy run folders, it reports `legacy/inferred` and lists discovered artifacts.

### `flow run history <work-id>`

Show one run's append-only transition history from `.flow/runs/<work-id>/events.jsonl`.

Flags:

- `--json` — emit JSON

Legacy/inferred runs may have no history; that is reported as an empty event list rather than creating one.

### `flow run verify <work-id>`

Check a run's state/history consistency.

Flags:

- `--json` — emit JSON

For C-lite runs, verification checks schema version, presence of transition history, latest event state, and `last_event`. For legacy/inferred runs, verification succeeds with the explicit message `legacy/inferred: no canonical run.json`.

### `flow run validate-orchestration <work-id> --stage <stage>`

Read-only validation of `.flow/runs/<work-id>/orchestration.json`.

Flags:

- `--stage dispatch|handback|acceptance` — required cumulative validation stage
- `--json` — emit stable `ok`, `stage`, `manifest`, and `findings` fields

Dispatch checks briefs, evidence inventories, declared capabilities, output ownership, risk, and concurrency. Handback adds outputs, reconciliation, baseline, recovery, readback, comparison, and unexpected-delta checks. Acceptance adds identity provenance and high-risk verifier independence. Diagnostics identify the field, subject, rule, and corrective action without printing referenced artifact contents.

The command validates declarations. It cannot query hidden runtime grants, prove semantic truth, or establish transactional behavior for arbitrary external systems.

### `flow run transition <work-id> <event>`

Apply a hard-gated lifecycle transition. Invalid transitions and orchestration refusals leave `run.json` and `events.jsonl` unchanged.

Flags:

- `--artifact NAME=PATH` — record gate evidence or an artifact pointer; may be repeated
- `--disposition NAME=VALUE` — record a closure disposition; may be repeated
- `--note TEXT` — record a next action or transition note
- `--json` — emit JSON

Core path events:

- `start-definition`
- `approve-definition` — requires `--artifact requirements=...` and `--artifact acceptance_criteria=...`
- `start-solution`
- `approve-solution` — requires `--artifact solution=...` and `--disposition risk=...`
- `start-plan`
- `approve-plan` — requires `--artifact plan=...`, `--artifact handoff=...`, and `--artifact validation_plan=...`
- `start-implementation`
- `mark-handback-ready` — requires `--artifact implementation_evidence=...` and `--artifact handback=...`
- `start-review`
- `accept-review` — requires `--artifact review=...`
- `archive` — requires `--disposition capability_gaps=...` and `--disposition memory=...`

Support events:

- `pause`
- `block`
- `resume`
- `archive-scout` — creates the minimal scout closure envelope and requires `--artifact scout_summary=...`, `--disposition capability_gaps=...`, and `--disposition memory=...`

`flow run transition` is the only command that writes lifecycle state. `/flow-*` commands call it when they cross gates; they do not hand-edit `run.json`.

New runs are protocol revision 2 while `run.json` remains schema 1. Their definition, solution, and plan approvals require `--artifact orchestration_manifest=.flow/runs/<work-id>/orchestration.json` and dispatch validation. Handback and review acceptance re-run the later stages. Runs without `protocol_revision` are revision 1 and retain the previous behavior. A scout remains lightweight unless it supplies an orchestration manifest, in which case `archive-scout` validates acceptance.

### `flow runtime smoke`

Check generated Claude and Codex runtime adapter surfaces and list the manual
runtime smoke evidence still required.

Flags:

- `--target all|claude|codex` — runtime target to check (default: all)
- `--json` — emit JSON

Static checks prove local generated files only:

- managed manifests exist and cover desired outputs
- generated surfaces are fresh against the current scaffold/user-overlay manifest
- generated command skills exist
- command skills include Flow Agent Routing
- lifecycle command skills include the C-lite run protocol text
- generated agents exist
- generated agents contain the model and effort fields resolved from `flow.toml`
- generated hooks exist

Manual-required checks are intentionally not treated as failures:

- invoke a representative command in Claude and Codex and confirm it loads
- invoke a low-risk role agent such as `support-lead`
- inspect transcript or runtime log evidence for configured model and effort
  where the runtime exposes it

This command is read-only. It exits 1 only when a static check fails. It does
not claim that local files prove the client honored model routing at runtime.

### `flow doctor`

Report machine, install, user-level, and project-level state in one output.

Flags:

- `--json` — emit the same support facts as a structured diagnostic payload.
- `--check` — exit nonzero when any error- or warning-severity diagnostic is present.

Current sections:

- **machine** — Python, flow home, source path, scaffold availability, config, launcher
- **install** — install mode (develop or release), version (release only), source target (develop only), installed_at timestamp
- **user-level** — Claude/Codex sync state and drift for `~/.claude/`, `~/.agents/skills/`, and `~/.codex/`
- **project** — repo `.flow/` presence, manifest, whether the overlay still carries framework copies, how many of its files have drifted from the framework, project-local runtime adoption surfaces, each `[[replaces]]` wiring's status, and whether `PROJECT.md` still lists the retired project-standards section

The overlay count and the drift count are reported **separately and never summed**. `overlay:` counts what `flow project migrate` removes by default and can therefore drive to zero, which is what lets that line name that command. `drifted:` counts files that differ from the framework, which is not clearable the same way — removing one is opt-in and may destroy a customization. Summed, the number would name a remedy that cannot reach it, and doctor would report a permanent fault where there is none. A drifted overlay with nothing removable reads `overlay: clean` alongside a `drifted:` line, and both are true.

The `replaces:` block appears only when the project declares wirings. Each is reported as `ok` (the replacement resolves in your user overlay), `absent` (it does not resolve *on this machine* — a wiring names a path under `~/.flow/user/` that a teammate may not have, so this is a gap in your overlay rather than a fault in the project), `unknown` (the `default` names no framework file, so the wiring can never match), or `invalid` (the entry did not validate). In `--check` mode, any warning or error diagnostic makes the command exit nonzero.

The `adoption:` line reports project-local runtime directories that Flow does
not own through user-level sync. Directories such as `.claude/`, `.codex/`, and
`.agents/` are `unmanaged` until you remove stale generated content or declare
intentional project ownership in `.flow/flow.toml` with
`[[adoption.exclusions]]`. Invalid exclusions appear as `adoption config:` so a
typo does not hide a real adoption gap.

The JSON payload uses stable diagnostic items with `id`, `status`, `severity`, `category`, `summary`, and optional `target`, `path`, `detail`, and `next_action`. Categories include `missing`, `parse_error`, `permission_denied`, `git_unavailable`, `remote_unreachable`, `manifest_invalid`, `managed_conflict`, `runtime_not_found`, `drift`, `stale`, `manual_required`, `warning`, and `ok`.

Use this as the main diagnostics command.

### `flow install --release`

Convert an existing develop install from symlink mode to release mode. This is mode conversion, not the normal first-install path. The clone is **not** deleted — the user controls its lifecycle.

Behavior:

- Resolves the symlink target as the source clone
- Determines version via `git describe` in the clone (exact tag → base tag + dev sha → `main@<sha>`)
- Copies the release roster (`cli/`, `scaffolds/`, `hooks/`, `scripts/`, `docs/`, `README.md`) into a staging directory under `~/.flow/`
- Validates staging. It must contain `cli/flow.py` (which has to parse), `scaffolds/default/flow.toml`, and `data/harness_capabilities.json`. Every module-scope import reachable from the staged `flow.py`, followed transitively, must also resolve — either as a file under the staged `cli/`, or as something importable from the current environment. The set is read out of the staged entrypoint rather than kept as a list in the validator, because this check runs from the *installed* version against a *newer* tree, so any hand-maintained roster would be behind by construction. Resolution rather than classification, for the same reason: an older install cannot know whether a new name is a flow module or a package flow started depending on, and guessing would let it reject a valid future release with no way to ship the correction.
- Atomically swaps the staging directory into `~/.flow/source/`
- Updates `~/.flow/config.toml` with `mode = "release"`, version, remote, and installed_at

Use this when a contributor's machine is ready to switch off development mode and pin to copied release content.

### `flow install --develop <clone-path>`

Convert the current install from release mode (copied directory) to develop mode (symlink to a clone).

Behavior:

- Validates that `<clone-path>` contains `cli/flow.py`
- Removes the copied directory at `~/.flow/source/`
- Creates a symlink from `~/.flow/source` to the given clone
- Updates `~/.flow/config.toml` with `mode = "develop"`, `source_target = <clone-path>`, and installed_at

Use this when switching back to maintainer mode against a working clone.

### `flow update`

Roll forward a release install to the latest semver tag from the configured remote.

In release mode:

- Calls `git ls-remote --tags --refs` against the configured remote
- Picks the highest semver-ish tag (`vMAJOR.MINOR.PATCH[-suffix]`)
- Clones that tag into a temp directory
- Stages and validates the new content, then atomically swaps into `~/.flow/source/`
- Updates `~/.flow/config.toml` with the new version and installed_at

In develop mode: prints the manual `git pull` + `flow sync ... --user` commands; takes no other action.

Flags:

- `--check` — report current vs latest version without applying. When a newer version is available, also fetches `CHANGELOG.md` from the remote at the new tag (via a sparse partial-clone — only the one file is actually downloaded) and prints the `## [<version>]` section so you can see what's in the available release. Falls back silently if no CHANGELOG entry exists for that version.
- `--resync` — after applying, also run `flow sync claude --user` and `flow sync codex --user`
- `--remote URL` — override the remote configured in `~/.flow/config.toml` (useful for testing)
- `--json` — with `--check`, emit classified update diagnostics for support automation

The update is atomic: staging is validated before any rename happens, so a failed clone, broken staging, or swap error leaves the existing install intact. A successful update keeps no rollback state — to revert, run `flow update --remote <url>` against an older tag or re-run `install-flow.sh --release` from a checkout at the desired version.

### `flow sync claude --user`

Generate the Claude runtime adapter surface at user level, from the framework scaffold.

Outputs, all under `~/`:

- `~/.claude/skills/...`
- `~/.claude/agents/...`
- `~/.claude/hooks/...`
- `~/.claude/settings.json`
- `~/.claude/flow.managed.toml`

If `~/.flow/user/flow.toml` exists, the user overlay merges on top of the framework manifest before generation: same-name commands and shared agents override the framework entry, new names append. User-origin entries in the managed manifest carry `~/.flow/user/...` source paths so origin stays auditable. See `docs/architecture.md` "User Overlay" for the merge semantics.

### `flow sync codex --user`

The Codex twin. Outputs `~/.agents/skills/...`, `~/.codex/agents/...`, `~/.codex/hooks/...`, `~/.codex/hooks.json`, and `~/.codex/flow.managed.toml`.

### `flow sync <target> --user --check`

Report drift without writing files. Exits 1 when the generated surface is out of date, which is the difference between this and `flow project audit` — drift in a generated adapter is a repairable fault, so it fails; a contaminated project overlay is a normal state, so that does not.

Add `--json` to emit the same result as a structured diagnostic payload. Sync check diagnostics use the shared category vocabulary, including `ok`, `drift`, `stale`, `managed_conflict`, `manifest_invalid`, `missing`, and `runtime_not_found`.

### `flow sync <target>` without `--user`

**Retired.** Prints a pointer and exits 1.

Project-level sync existed to regenerate a repo's own `.claude/` and `.codex/` adapters from that repo's own copies of the framework's commands and agents. Both halves of that are gone: projects no longer hold copies, and `flow setup project` no longer creates them. Runtime surfaces are installed once at user level and apply in every session.

It exits 1 rather than printing a note and succeeding, because a pointer alongside a zero exit is indistinguishable from having synced — any caller checking the exit code would carry on believing its adapters were current.

To remove the adapters an earlier project-level sync left behind in a repo, use `flow project migrate`.

Use `flow setup user` for the initial install; use `flow sync <target> --user` to re-sync after framework changes.

### `flow harvest claude`

Read Claude Code session transcripts from `~/.claude/projects/` into the usage store's raw layer at `~/.flow/usage.db`.

Behavior:

- incremental — resumes from the last-read position per file, so re-running is cheap
- writes session and turn records; reads nothing over the network
- creates the store on first use

Flags:

- `--rescan` — rewind already-recorded files' watermarks first and re-read them from the start
- `--since DATE` — with `--rescan`, only rewind files modified on or after `DATE` (`YYYY-MM-DD` or a full ISO timestamp)
- `--session ID` — with `--rescan`, only rewind files whose path contains `ID`
- `--dry-run` — with `--rescan`, report the scope and exit without writing anything

Use this when you want the store current before a read-only cost view. `flow cost active` and `flow cost verdict` run the relevant live harvest path for their own surfaces.

#### When you need `--rescan`

A plain harvest only reads what is new since last time, so a collector improvement never reaches transcripts already on disk. `--rescan` re-reads them. Three things only it can recover:

- **full output-token counts.** A streamed response is written as several transcript lines that share one request id, and only the last carries the final `output_tokens`. Collectors before v3 kept the first, storing a partial count — about a third of the real output, measured against the console.
- **compaction events.** `compact_boundary` records were dropped entirely before collector v3.
- **titles, `cwd`, and title provenance** for sessions harvested before those were captured.

Safe to run repeatedly. The output-token rule is highest-wins, which is order-independent, so a rescan cannot un-correct a row it already fixed.

Rescanning the whole corpus re-reads every recorded transcript. Rehearse the filters first:

```
flow harvest claude --rescan --since 2026-08-01 --dry-run
flow harvest claude --rescan --since 2026-08-01
```

`--session` takes a session uuid and matches it against file paths, which reaches that session's main transcript and its subagent files together.

A transcript deleted from disk cannot be rescanned — its stored turns keep whatever the collector recorded at the time, permanently.

`--backfill` is the former name of `--rescan` and still works. It is hidden from `--help`; prefer `--rescan`.

### `flow harvest codex`

Read Codex session transcripts from `~/.codex/sessions/` into the usage store's raw layer. No flags.

Behavior:

- incremental and resumable, the same as the Claude harvest
- `flow cost active` runs this automatically when `~/.codex/sessions/` exists, because active status is a current-state view
- read-only views do not run it; they report freshness and name the manual refresh path when Codex data may be stale

Use this whenever you care about Codex totals being current before `summary`, `sessions`, `trend`, or `baseline`.

### `flow normalize`

Project every harness's raw turn records into one shared token convention.

Behavior:

- only rows without a current-version normalized counterpart are recomputed, so this is safe and cheap to re-run

Use this after a manual harvest, before reading `cost summary`, `cost sessions`, `cost trend`, or `cost baseline`. `flow cost active` and `flow cost verdict` normalize for their own current-state reads.

### `flow cost summary`

Token totals grouped by harness and model, plus the most recent Codex capacity reading as a separate gauge line.

Flags:

- `--days N` — show the last N days (default: 7)
- `--all` — show every row ever normalized; cannot be combined with `--days`
- `--json` — print the same result as JSON instead of an aligned table

Reads only the normalized layer — it does not harvest, so what it shows is as current as your last harvest/normalize pass. It includes freshness metadata in JSON and a freshness note in text output when the store is empty, stale, partial, or unreadable. Prints `(no data in range)` when the window is empty.

**The capacity line is a snapshot with an expiry.** It renders the reading's own `resets at` time beside `as of`, and it disappears entirely once that time passes — an expired gauge is absent, not dimmed. Primary and secondary expire independently. A reading sampled more than halfway through its own window is still shown, with a note: it is valid, but usage has had most of the window to move since.

### `flow cost trend`

Efficiency per time bucket — the view that answers "is my session hygiene actually working," which the level-reporting views cannot.

One row per **bucket and harness**, not per bucket. Blending them would mean summing token classes whose semantics differ: Codex's cached input is a subset of its input, where Claude's cache buckets are disjoint and additive.

Flags:

- `--days N` — show the last N days (default: 7)
- `--all` — every row ever normalized; cannot be combined with `--days`
- `--bucket day|week` — bucket size (default: day)
- `--harness claude|codex` — restrict to one harness (default: both)
- `--json` — JSON instead of an aligned table

Columns:

| Column | Meaning |
|---|---|
| `turns` | main-agent turns (sidechains excluded) |
| `sessions` | distinct sessions with a main-agent turn in the bucket |
| `ctx/turn` | mean context per main-agent turn |
| `in:out` | total input over total output |
| `wt/1k out` | **weighted tokens per 1,000 output** — the headline |
| `sub%` | subagent share of weighted tokens |
| `cmpct man` / `cmpct auto` | compaction events, split by trigger |
| `med pre man` | median context at the point of a manual `/compact` |

`wt/1k out` collapses the input classes by billing multiplier (uncached 1.0, cache read 0.1, 5m write 1.25, 1h write 2.0) and divides by output. Dividing by output is what makes it an efficiency number rather than a busyness number — raw daily burn conflates working less with working leaner. The multipliers live in `data/token_weights.json`, so a pricing change is a data edit rather than a release.

`wt/1k out` and `sub%` are blank for Codex. The weights are Anthropic cache multipliers, Codex reports no cache writes at all, and its cache-read semantics differ — the same arithmetic would not mean the same thing.

Manual and auto compactions are never summed. A manual `/compact` is deliberate hygiene; an auto one is hitting the ceiling. They are opposite signals about a session's health, and `med pre man` is the useful companion: how full the context typically was when you chose to cut.

**Buckets follow your local calendar, not UTC.** Stored timestamps are UTC and every window comparison stays UTC, but a bucket is a label on a human day: bucketing by UTC splits an evening across two rows for anyone west of Greenwich, and on the corpus this was built against that moved 7% of a week's turns off the day they happened. A week is keyed by its **Monday's date** rather than a week number — `%W` counts weeks within a calendar year, so a week spanning New Year would otherwise split into two partial buckets and skew every volume column.

Read-only, and it does not harvest first — a trend over completed periods does not become wrong for want of the last few minutes.

**Coverage is labelled, never silently truncated.** If the window reaches back before the earliest harvested turn for a harness, a note says so. Absent buckets and empty buckets are different facts, and hiding the difference turns a coverage gap into a false trend.

### `flow cost baseline`

The always-on token floor — what a session costs to *open*, before any work happens — and the changes that moved it.

Every session pays a static prefix: system prompt, tool definitions, MCP server instructions, agent and skill descriptions, `CLAUDE.md`, memory files. Every other `cost` view measures what a session spent; this one measures where it started. The distinction matters because enabling a plugin raises the opening cost of every future session, permanently and invisibly.

Flags:

- `--days N` — show the last N days (default: 7)
- `--all` — every bucket ever normalized; **this is the useful invocation**, since a changepoint log needs more than one bucket to compare
- `--harness claude|codex` — restrict to one harness (default: both)
- `--by-cwd` — estimate per working directory instead of pooling, one block per directory
- `--json` — JSON instead of the rendered block

**The estimator is `cache_read_tokens` on a session's first turn.** At that point no conversation exists, so the number is the cached static prefix and nothing else — the opening message and any SessionStart hook output land in `fresh_input_tokens` instead. The obvious alternative, `fresh + cache_read + cache_write`, is available on more sessions but reads high for exactly that reason.

A session qualifies only when all four hold. Each rule removes a different way a turn can look like a first turn without being one:

| Rule | Removes |
|---|---|
| minimum `turn_seq` among non-subagent turns | a subagent turn that precedes the main thread in the file |
| `source_line_no` at or below the threshold | sessions where the collector first attached mid-file, so its earliest row is mid-conversation |
| no `compact_boundary` at or before the turn | resumed sessions, which restart with a summary already in context |
| `cache_read_tokens > 0` | cache misses, which carry no prefix reading at all |

`cache_read_tokens = 0` means **cache miss, not new conversation.** The prompt cache is keyed by prefix hash across the account rather than per session, so a genuinely new session started soon after another with the same prefix reads the whole thing from cache. Those are the good observations here.

**Reported at p10, not a mid-range quantile.** Prefix readings are not a distribution — they are a few exact, repeated plateaus, because the cache returns the same number for every session sharing a prefix. One measured week had all 13 of its sessions read 22,489; another had all 41 read 21,830. When two configurations coexist in a week, a mid-range quantile tracks the *mix* between plateaus rather than the floor, and jumps when the mix shifts. On the corpus this was built against, p25 manufactured a +35% spike and a −28% return across weeks in which nothing changed. p10 is flat there, and equals the minimum in every measured week.

**A change registers only when it clears both 15% and 2,500 tokens.** Either bound alone misfires at one end of the range. The consequence is stated in the output rather than hidden: a change smaller than that is invisible here. This detects deliberate reconfiguration, not gradual creep — one plugin quietly returning will not show up.

**Changes are detected within a series, never across two.** Pooled, that is one series over time. Under `--by-cwd` it is one series per directory, each with its own headline and history — two directories in the same week are not a sequence, and comparing them would report the gap between two projects as a change over time.

**Both endpoints of a change are shown, and skipped weeks are marked.** Buckets exist only for weeks that had observations, so two adjacent rows can be months apart. A change reported as `2026-06-22 -> 2026-07-06` with a "weeks skipped" note happened somewhere in that span, not necessarily in the later week.

Pooled across projects by default. `--by-cwd` is available but fragments the population quickly: on the corpus this was built against, 166 observations spread over 24 directories left only three with 20 or more. It is also largely unnecessary — the floor's dominant contributors are global, and the three directories with enough observations to compare agreed to within 6%.

The pooled figure has a known sensitivity, disclosed in its own output: it reports the *leanest project's* prefix, so a week that adds sessions from a lighter directory lowers it without any configuration changing. This is the same failure mode that ruled out p25, one level up, and it can only be disclosed rather than filtered away.

`compaction filtering:` distinguishes capability from coverage. A store harvested before the collector began recording `compact_boundary` has the capability and no rows, and says so rather than claiming a filter that matched nothing.

A bucket below the minimum sample keeps its row and its count but reports no floor. A thin week and a week with no sessions are different facts, and a quantile over a handful of sessions is noise dressed as a measurement.

No `~` markers. Unlike an inferred context window, every figure here is a value some session actually reported.

Read-only, no harvest, no schema. Like every other `cost` surface, it measures this machine only.

### `flow cost sessions`

Token totals grouped by session, most recently active first.

Flags:

- `--days N` — show the last N days (default: 7)
- `--all` — every row ever normalized; cannot be combined with `--days`
- `--json` — JSON instead of an aligned table
- `--limit N` — cap the sessions shown (default: 20; `0` = unlimited)

Same reading-only behavior as `summary`.

### `flow cost active`

Per-active-session context percentage, carry above session start, idle time, and a `/clear`-or-`/compact` recommendation — worst carry first.

Behavior:

- runs the incremental Claude harvest, runs the incremental Codex harvest when `~/.codex/sessions/` exists, and runs a normalize pass **first**, so the answer is current without a separate step for local transcripts
- prints `(no active sessions in range)` when nothing qualifies

Flags:

- `--within N` — count a session as active if its latest turn is within N minutes (default: 60)
- `--json` — JSON instead of an aligned table

A session is recommended for `/clear` or `/compact` once its carry clears `25,000` tokens and it has at least `15` requests behind it — the request minimum exists so a young session with one huge turn is not graded on a single sample. Both are fixed constants in `cli/cost.py`, not configurable.

**How the context window is resolved**, best source first:

1. the statusline's exact record for that session
2. `preTokens` at an **auto** compaction in that same session — auto fires at the ceiling, so it is a direct observation of what the session held. Scoped to that session and never generalised to the model: the same models run in 200K sessions constantly, so a model-wide rule would divide every one of those percentages by five
3. `data/model_context_windows.json`, marked `~` — a model string carries no window suffix, so a 1M session under the threshold reads as standard and its percentage is overstated
4. nothing — for a model absent from that file, `ctx` and `carry` show `?` and no recommendation is given. An honest blank beats a confident wrong number, and it is the signal that the file needs a new entry

The `sub` column is the subagent share of that session's weighted tokens. `ctx` and `carry` measure the main thread only, so work moved into subagents leaves both looking better without costing less — the two are shown together so that improvement can be told apart from a real one.

Use this as the interactive view; it is also what the workflow commands consult for their cost posture check.

### `flow cost verdict`

Live `/clear`-or-`/compact` judgment for a single session: harvests that transcript incrementally, normalizes, and judges carry from the store.

Exactly one flag is required:

- `--transcript PATH` — print the judgment line for this transcript; silence means there is nothing to say
- `--hook` — Stop-hook mode: read hook JSON from stdin, write or remove the verdict file, print nothing

`--hook` is the engine behind the generated Stop hook. Stop's stdout reaches the transcript rather than the model, which is why this writes a file instead of printing. That file is `/tmp/<harness>-verdict-<session_id>` — `/tmp/claude-verdict-...` is also what the Claude statusline reads, a filename contract that predates flow.

Use `--transcript` to ask the question by hand; leave `--hook` to the generated hook.

### `flow cost warn`

Pre-execution context advisory. Requires `--hook`.

Behavior:

- reads the verdict file the Stop hook last wrote — no computation at prompt time
- prints one line only when carry exceeds `100,000` tokens **and** has grown by another `50,000` since the last warning. The re-warn step exists because an advisory that repeats every prompt trains you to ignore it, and each firing spends real context in the conversation it lands in
- informational only; always exits 0

Both thresholds are fixed constants in `cli/cost.py`. Use this only through the generated `UserPromptSubmit` hook — invoking it by hand tells you nothing the verdict file does not.

### `flow plugin-usage snapshot`

Records the harness's plugin and skill usage counters into the store, if they have moved since the last look.

Flags:

- `--hook` — SessionStart-hook mode: shorter busy timeout, prints nothing, always exits 0

Every other flow surface measures what a session cost. This one is the write half of measuring whether the configuration that cost it is being used at all. The evidence is counters the harness maintains in its own config — values flow did not create and cannot re-derive from anything else on disk.

**Two writers, no coordination.** A SessionStart hook samples on every session, and `flow harvest claude` samples as a backstop. Neither locks against the other, because observations are keyed by their *content* — `(harness, host_id, kind, name, usage_count, source_mtime)` — so two writers that saw the same file revision produce identical rows and the second is a no-op. No delta is stored at all, which removes the race worth caring about: a writer arriving second cannot compute a change against a row the first just wrote.

**The mtime guard is the cost control.** The harness config runs past 150 KB, so the command stats it, compares against the recorded watermark, and only parses on a change. This is also why the hook runs on SessionStart rather than Stop: the file is rewritten every few seconds during a session, so a Stop hook would find it changed almost every turn and parse it every time.

Claude only. Codex maintains no equivalent counters, which `data/harness_capabilities.json` records as `plugin_usage_counters = 0`.

**What lands in the store:** plugin and skill names, their integer counters, a timestamp, and the working directory the skill inventory was scanned from. Nothing else from the harness config is read — not MCP server definitions, not credentials, not project entries. The scanned directory is recorded because the installed-skill population depends on where the scan ran, and it accumulates one row per distinct directory over time. `flow doctor` renders it home-relative, but the absolute path is what the store holds, so bear that in mind before sharing `~/.flow/usage.db` itself.

### `flow plugin-usage show`

The report `flow doctor` renders as a section, standalone.

Flags:

- `--json` — the payload instead of the rendered section

The JSON payload includes a `freshness` object. In text mode, a freshness line appears when the history is thin, stale, empty, or needs a manual snapshot. This keeps plugin usage in the same support model as cost freshness without treating hook firing counts as deliberate invocations.

**Hook firings are reported separately from deliberate invocations, and this is the point of the surface.** The harness increments a plugin's counter once per hook firing, so a plugin's number measures how many hook events it declares rather than anything a person did. On the machine this was built against, one plugin registering five hook entries read 16,373 while a plugin invoked deliberately read 1 — three orders of magnitude apart, in the same field, meaning different things. They never share a column, and the hook block says so in its own heading.

**Plugins and skills report zero differently, because their maps disagree.** `pluginUsage` is seeded at install, so a plugin present at zero is a real reading of "never used". `skillUsage` is written on first use, so it holds no zeros at all and an unused skill is simply *absent*. Identifying unused skills therefore needs a separate walk of the installed skills, and the result is marked `~` because it is inferred rather than reported.

**Counter keys that match no installed skill get their own line.** They are renamed, uninstalled, or from a marketplace that no longer exists; on the corpus this was built against, 40 of 73 keys no longer resolved. They are surfaced rather than dropped, because losing more than half the evidence silently would leave output that looks clean and is not.

**Namespace variants are shown separately and never summed.** One plugin can appear under two map keys — a marketplace one and an `inline` one. Whether those counters double-count the same invocations or count disjoint ones is unverified, so a total is not offered. The namespace is printed only where a base name has more than one variant, because a namespace truncated to fit a column disambiguates nothing.

**A plugin whose counter outlived its install gets its own block.** Counter keys persist after uninstall, and hook detection reads the install directory — so a departed plugin cannot be classified at all. Reporting it under deliberate invocations would render an uninstalled hook plugin's firings as calls, which is the original error exactly. Absence of evidence is reported as absence of evidence.

**A reset plugin is not a never-used plugin.** A counter reset to zero satisfies "zero invocations" while meaning something different: its history stopped being comparable at the reset. It is excluded from the prune list and reported as a reset instead.

**A thin history reports as thin,** and maturity is elapsed time *and* sample count — five snapshots spanning a week, not five snapshots. The hook fires on every session start, so a count-only gate would call a same-day store mature and release the "never invoked" list on it.

**Rows record changes, not observations.** A counter that has not moved writes no new row, so the table grows with usage rather than with how often the harness rewrites its config. One consequence is worth knowing: a delta of zero cannot occur. Movement is a delta, no movement is the absence of a row, and `last_used_at` carries recency. A displayed delta is the size of the most recent change, not a per-snapshot difference.

History cannot be backfilled — the harness keeps none — so this reports only what flow has observed since it started looking, and the header says how many snapshots that is. Read-only; measures this machine only.

### `flow gaps add`

Records one capability gap observed during a run. Run by `flow-archive`, not usually typed by hand.

Flags:

- `--key` — short slug identifying the gap; **reuse an existing key to mark a repeat**
- `--summary` — what the framework was missing
- `--project` — the project the run belonged to
- `--run` — the work id of the run that observed it
- `--at` — ISO timestamp, defaults to now
- `--ledger` — ledger path, defaults to `~/.flow/user/capability-gaps.jsonl`

**Repeats are detected by the key you supply, never by matching text.** Gap descriptions are free prose, so exact matching would never fire and fuzzy matching is a guess dressed as a measurement. The agent reads the existing keys with `flow gaps list` and reuses one when the new gap is the same gap. Counting stays exact and the judgment stays with the reader — but nothing enforces the discipline, and a careless key silently starts a second lineage for one problem.

**Idempotent on `(key, run)`.** The same key twice in one run is a re-run of the archive, not a recurrence. Inflating the count there would make the one number this surface exists to produce untrustworthy.

### `flow gaps list`

Groups recorded observations by key, most-observed first, with each sighting's project and run.

Flags:

- `--json` — the payload instead of the rendered table
- `--ledger` — ledger path

A key with more than one sighting is a gap that recurred *after* being noticed. That is the signal the surface exists for: while observations sat in separate run artifacts, three sightings of one problem read as three unrelated notes.

**A malformed line is skipped and counted, not fatal.** One bad line from a partial write must not make every recorded gap unreadable, and the skipped count is printed so the damage is visible rather than swallowed.

### `flow gaps promote`

Writes one gap into the flow repo's `docs/backlog.md`.

Flags:

- `--key` — the gap to promote
- `--at` — ISO timestamp, defaults to now
- `--ledger` — ledger path

**Promoted entries land under `## Deferred / Watch`, never under `## Active Priorities`.** Active Priorities is an ordered list whose order is the maintainer's judgment; inserting into it — even at the end — is a ranking claim about an item that has had no triage.

**Requires `~/.flow/source` to be a git work tree.** A release install copies the framework in and deletes the clone, so there is no backlog to write; there the command prints a paste-ready entry and exits 0. That is the ordinary outcome for most installs, not a fault. Membership is asked of git rather than inferred from a `.git` directory, because `~/.flow/source` is normally a symlink.

**Never commits and never pushes.** Promoting and publishing are separate decisions, and the second is the engineer's alone. The command deliberately stops having left the working tree dirty, so the change is staged for a human to read before it goes anywhere.

**The promoted entry carries the gap and its count, never the project or run that produced it.** The ledger is personal and lives in a private overlay; `docs/backlog.md` lives in the flow repository, which does not share that audience. The count is the half that makes a repeat actionable and the provenance is the half that identifies the work, so only the first crosses over.

**Promotion is recorded as a second event, not a flag on the first.** Rewriting a line mid-file is the only operation that can corrupt an append log, and a flag would discard when the promotion happened. Promoting twice is refused and leaves the backlog byte-identical.

If the backlog is missing, or its anchor heading is absent or duplicated, the command refuses and hands back the entry rather than guessing where a section starts in a document someone has restructured.

### `flow project audit`

Classifies this repo's `.flow/` overlay against the installed framework scaffold. Read-only.

Flags:

- `--json` — the payload instead of the rendered report
- `--root PATH` — audit this `.flow` directory instead of the enclosing repo's
- `--scaffold PATH` — compare against this framework scaffold instead of the installed one

`flow setup project` copies the entire scaffold into a repo, and those copies never update. A project set up months ago is running framework files nobody has touched since, and nothing on the machine says so — the copies are byte-identical to files the user never edited, so they read as deliberate customization. This command is what separates the two.

Five buckets:

- **identical** — byte-equal to the framework's copy
- **differs** — the framework has this file and the contents are not equal
- **project-only** — no framework counterpart
- **orphaned** — declared in `flow.toml`, absent on disk
- **conflict** — the path exists but is not a file where the framework has one
- **unreadable** — listed on disk but could not be read, so could not be compared

Two things are reported outside the buckets, because neither can be safely acted on. **Symlinks are never classified** — a symlinked capability directory produces innocuous-looking relative keys that resolve outside the overlay, and the whole point of relative keys is that joining one against the root stays inside it. **Manifest sources that are absolute, contain `..`, or start with `~`** are listed as unusable declarations rather than as orphans, and they carry no joinable path at all.

Runtime adoption surfaces appear in their own section. Audit checks
project-local `.claude/`, `.codex/`, and `.agents/` directories. Each entry is
`absent`, `unmanaged`, or `excluded`. `unmanaged` means the directory exists and
Flow needs a decision: move project-owned content into `.flow`, remove stale
generated files through the migration/sync workflow, or record intent with
`[[adoption.exclusions]]` in `.flow/flow.toml`:

```toml
[[adoption.exclusions]]
target = "claude"
path = ".claude"
reason = "project keeps hand-authored Claude config"
```

Valid targets are `claude`, `codex`, and `project`. Paths must be relative.
They must not start with `~` or escape the repo with `..`. Invalid entries
appear in `invalid adoption exclusions` and in the JSON payload under
`rejected_adoption_exclusions`. Valid entries appear under
`adoption_exclusions`. The runtime inventory appears under `runtime_surfaces`.

**`differs` cannot be split locally, and the report says so.** A file that differs is either a real customization or a stale copy of a framework file that has since moved on, and nothing on this machine can tell which — the overlay records no provenance. The caveat is printed with the count rather than left in this document, because the count is what gets pasted into a ticket.

**Only capability paths are walked: `standards/`, `templates/`, `commands/`, `agents/`, `project/`, and `FRAMEWORK.md`.** `PROJECT.md`, `flow.toml`, `memory/`, and `runs/` are the project's own state and are never visited. That is the safety property rather than a scoping convenience — a path this command never classifies cannot be proposed for deletion by anything reading its output. The report names what it skipped, so a 71-file overlay reporting 48 classified entries reads as a deliberate scope rather than a broken scanner.

**`flow.toml` is read as input, never classified.** It is how orphans are found. It also differs from the framework's copy in every real project, so classifying it would report a permanent false positive.

**Exits 0 whatever it finds.** This diverges from `flow sync --check`, which exits 1 on drift, and the difference is deliberate: drift in a generated adapter is a repairable fault, while a contaminated overlay is the normal state of every project set up before the overlay was thinned. A non-zero exit there would fail in every pipeline it ran in and train everyone to ignore it.

It exits 1 only when no audit could be produced: there is no `.flow` here, the path resolves inside flow's own home rather than a project, `--root` is not a directory, or the framework scaffold holds none of the capability directories. That last one classifies nothing at all — not in the table and not in `--json` — because without a baseline every file would come back `project-only`, which is wrong rather than clean.

**`--scaffold` decides what `identical` means.** Pointed at a project's own overlay it makes every file identical, which is the bucket a migration deletes, so the payload records whether the comparison used the installed framework (`default_scaffold`) and the report says so in a note above the buckets. Audit still performs the comparison — it deletes nothing, and comparing a tree against itself is a legitimate thing to ask for — but the note exists because `identical (75)` otherwise reads as an invitation to migrate, and `flow project migrate` refuses this exact comparison. A `--scaffold` pointed at a *subdirectory* of the overlay hits the no-baseline guard first instead, which is the more specific message.

**Nothing here deletes.** Acting on the report is a separate verb, and it reads this one's output.

### `flow project migrate`

Acts on what `flow project audit` reports. **Dry run by default** — prints what it would do and exits 0 without touching anything.

Flags:

- `--json` — the plan instead of the rendered report
- `--root PATH` — migrate this `.flow` directory instead of the enclosing repo's
- `--scaffold PATH` — compare against this framework scaffold instead of the installed one
- `--drifted` — also remove files that differ from the framework; on its own it lists them and exits

Two things are removed: byte-identical copies of framework files under `.flow/`, and the `flow.toml` declarations that name a source which is gone or about to be.

**Only `identical` is removed by default.** A file in the `differs` bucket is either a real customization or a stale copy of a framework file that has since moved on, and nothing on this machine can tell which — so it is reported and left.

**`--drifted` is the exit from that state, and it is list-then-confirm.** On its own the flag prints the drifted files and exits 0 without touching anything; only `--drifted --apply --yes` removes them. That shape is deliberate: deletion elsewhere in this command is confined to hash-provable redundancy, and these files are the one bucket where no proof exists. Receiving the list is not the same as consenting to it, so the two are separate invocations.

**A drifted file whose declaring site cannot be located is refused, individually.** For a framework copy an unresolved site is survivable — the file is byte-identical to the scaffold's and can be fetched back. A drifted file cannot be. Removing it while its declaration stays would leave the manifest naming something that exists nowhere but the backup, so it is skipped and named while the rest of the run proceeds.

**The manifest is edited as text, not parsed and rewritten.** There is no TOML writer in this codebase, and the fallback parser drops comments and formatting. Each declaration is located in the manifest's own bytes by the dotted site the audit recorded, its line range is cut, and everything else survives byte-for-byte. A declaration that cannot be located is reported and left in place rather than guessed at.

**Array entries go whole; `[standards.*]` loses only its key.** A `[[claude.commands]]` entry with no `source` declares nothing, so the entry goes. A `[standards.x]` table can carry `spec` and `upstream` that outlive the source, so only the offending key line is cut.

**One source is often declared twice.** Every framework command appears under both `[[claude.commands]]` and `[[codex.commands]]`. Removing one and leaving the other is a dangling declaration, so the audit records every declaring site and migration removes all of them.

**The dry-run output is the whole informed-consent surface.** There is no interactive confirmation, so it prints the exact files, the exact declarations, an explicit list of what is being left alone — `project-only`, `conflict`, `unreadable`, and skipped symlinks — and the backup destination, before the decision rather than after it. Drifted files get their own block in one of two shapes and never appear in both the removal list and the left-alone list; a path under two headings is what stops the output functioning as a consent surface.

**`--scaffold` may not name the project's own tree.** Compared against itself every file is byte-equal, so the whole `differs` bucket — the files this command exists to protect — reclassifies as `identical`, and `project-only` files go the same way. The refusal tests resolved containment in both directions, not equality, because a subdirectory of the overlay is still the project's own tree. It fires at planning time, so the dry run and `--json` cannot describe a plan the command would decline to run. Any other scaffold is still accepted; the override exists for a reason.

It exits 1 for the same reasons `flow project audit` does: no `.flow` here, a path inside flow's own home, a `--root` that is not a directory, or a framework scaffold with no capability directories. Refusing without a baseline matters more here than there — every file would look project-only, so nothing could be classified as safe to remove.

### `flow overlay status`

The `doctor` overlay line on its own, plus the remote, the upstream, and the uncommitted paths behind its counts.

```
overlay:  ~/.flow/user
repo:     ~/dotfiles
vcs:      clean (main) — ~/dotfiles
remote:   git@github.com:me/dotfiles.git
upstream: origin/main
```

A `repo:` line appears only when the overlay is a subdirectory or symlink inside a larger repository, as above — in which case the counts on the `vcs:` line describe that whole repository, not just the overlay.

Read-only. Use this when `doctor` reports uncommitted or unpushed overlay work and you want to know which paths.

### `flow overlay check`

The overlay-commit advisory. Requires `--hook`.

Behavior:

- prints one line when the overlay's repository has uncommitted or unpushed work, throttled per event
- silent when the overlay is absent, untracked, ignored, or clean — so it costs nothing for anyone who has not opted in
- informational only; always exits 0

Throttle markers live in `~/.flow/state/overlay-nudge-<event>-<hash>[-<session_id>]`, keyed per repository, event, and session. Deleting one is how you make a suppressed advisory fire again.

Use this only through the generated `PostToolUse` and `UserPromptSubmit` hooks, on either runtime. Initialization lives in `flow setup user --overlay-repo`, not here; this command writes nothing but its own marker.

## Typical Sequences

### Maintainer Install From A Clone

```bash
cd ~/personal/flow
./install-flow.sh                  # develop mode (default)
# or: ./install-flow.sh --release  # release mode — clone is disposable after install
flow setup machine
flow setup user        # installs flow at user level — active in every supported runtime session
```

### Release Update

```bash
flow update --check    # see what's available
flow update            # apply atomically
flow update --resync   # apply + re-sync user-level adapters
```

### First-time project bootstrap (only for repos where you want a project overlay)

```bash
cd /path/to/project
flow setup project
flow bootstrap
flow project audit    # nothing to migrate in a fresh overlay; confirms it
flow doctor
```

Runtime surfaces come from the user-level install and need no per-project step.

### Framework update roll-forward

```bash
flow update --resync              # framework, plus user-level adapters
cd /path/to/project
flow bootstrap
flow project audit                # did the update leave stale copies behind?
```

### Drift-only check

```bash
flow sync claude --user --check
flow sync codex --user --check
flow project audit                # the project-overlay equivalent
flow doctor
```

## Failure Modes

### Missing `.flow/`

Symptom:

- `flow bootstrap` or `flow sync ...` reports that the repo is missing `.flow`

Fix:

- run `flow setup project`

### Missing manifest

Symptom:

- `flow sync ...` reports missing `.flow/flow.toml`

Fix:

- restore or refresh the project scaffold

### Unmanaged conflict

Symptom:

- sync reports unmanaged conflicts and stops

Meaning:

- a target runtime file exists, differs from generated content, and is not marked as previously flow-managed

Fix:

- move the real source change into `repo/.flow`
- or remove/rename the conflicting unmanaged runtime file
- then rerun sync

### Stale generated files

Symptom:

- `flow sync ... --check` reports drift

Fix:

- rerun the matching sync command without `--check`

### Empty cost output

Symptom:

- `flow cost summary` or `flow cost sessions` prints `(no data in range)`

Meaning:

- the store exists but holds nothing in the window. `summary` and `sessions` read the normalized layer and never harvest, so an empty result means nothing has been read in yet — or the window is too narrow

Fix:

- `flow harvest claude` and `flow harvest codex`, then `flow normalize`
- or widen the window: `--days 30`, or `--all`
- `flow cost active` harvests and normalizes on its own, so it is the quickest way to tell an empty store from an empty window

### Overlay untracked

Symptom:

- `flow doctor` reports `untracked — run flow setup user --overlay-repo <url> to give it history`

Meaning:

- `~/.flow/user/` holds authored content with no repository behind it: no history, no backup

Fix:

- `flow setup user --overlay-repo <url>`

### Overlay ignored by its enclosing repo

Symptom:

- `flow doctor` reports `ignored by <repo> — nothing here is committed despite the repo around it`

Meaning:

- the overlay sits inside a repository that explicitly excludes its path. This is the state worth naming separately, because a repo *is* present — the state looks handled while nothing in the directory is ever committed

Fix:

- find which rule owns it — `git check-ignore -v ~/.flow/user/flow.toml` prints the file, line, and pattern. It may not be the repo's `.gitignore`: `.git/info/exclude` and a global `core.excludesFile` both apply, and the overlay status call preserves `HOME` specifically so your own git config is honored
- remove the rule there, or move the overlay somewhere the repo tracks

### Overlay unreadable

Symptom:

- `flow doctor` reports `unreadable (git error)`

Meaning:

- a git call failed, so the state is genuinely unknown rather than clean

Fix:

- run `git status` in the overlay's repository directly and address what it reports

### A hook is installed but never says anything

Symptom:

- `flow cost warn` or the overlay advisory never appears, and there is no error either

Meaning:

- all three hook entry points are silent by design, so silence is the same shape as breakage. There is no symptom string to search for

Fix, in order:

- confirm the hook is registered — `flow sync claude --user --check` (or `codex`) should report no drift, and the entry should be present in `~/.claude/settings.json`
- read `~/.flow/logs/hook-errors.log`. These commands swallow their exceptions on purpose and leave one line per failure here; an empty or absent file means nothing has thrown
- confirm the store has data — `flow cost active` harvests first, so it distinguishes an empty store from a quiet one
- for the context advisory, check whether the verdict file exists at `/tmp/<harness>-verdict-<session_id>`; carry below `100,000` tokens is silence working correctly
- for the overlay advisory, delete the matching `~/.flow/state/overlay-nudge-*` marker to clear the throttle, then check `flow overlay status` — a clean overlay is also silence working correctly

### Corrupt or oversized usage store

Symptom:

- `flow cost ...` raises a SQLite error, or `~/.flow/usage.db` has grown larger than you want

Meaning:

- the store is a local cache, not a source of truth. Every record in it was derived from transcripts still on disk

Fix:

- delete `~/.flow/usage.db`, then `flow harvest claude`, `flow harvest codex`, and `flow normalize` to rebuild it. A full rebuild is not instant — expect tens of seconds once you have tens of thousands of turns on disk, since every transcript is re-read from position zero

## Install Scripts

flow ships two install scripts at the repo root:

- `install.sh` — bootstrap installer; the first-install path for most users
- `install-flow.sh` — local installer; used by the bootstrap and by maintainers running from a clone

### `install.sh` (bootstrap installer)

```bash
curl -fsSL https://raw.githubusercontent.com/andyconley/flow/main/install.sh | bash
```

This script (added in v0.4.4):

- queries the configured flow remote (`https://github.com/andyconley/flow.git` by default, override via `FLOW_REPO_URL`) for the highest semver tag
- shallow-clones that tag into a temporary directory
- delegates to that clone's `install-flow.sh --release` with `FLOW_VERSION_OVERRIDE=<tag>` so the install metadata records the exact tag the user asked for, even when multiple tags reference the cloned commit
- cleans up the temporary clone on exit

Use this when:

- a first-time install where the user doesn't want to keep a clone
- you want the latest released version without thinking about it

Requires `git` on the user's `PATH`. Public hosting of the curl URL requires the flow repo to be publicly readable; against a private repo, run `bash install.sh` from a local clone instead (the script's logic works either way once it can reach the remote).

### `./install-flow.sh [--develop|--release]` (local installer)

This script:

- creates `~/.flow/source` — either a symlink to the checkout (`--develop`, default) or a real copied directory (`--release`)
- writes the launcher to `~/.local/bin/flow`
- writes `~/.flow/config.toml` with `[flow]` and `[install]` sections (mode, version for release, source_target for develop, installed_at)

Modes:

- `--develop` (default) — symlinks `~/.flow/source` to the current checkout. Maintainer-shaped: edits in the clone go live immediately.
- `--release` — copies the framework into `~/.flow/source/` as a real directory using a **blacklist-based roster** (v0.6.1+): every non-dotfile top-level entry of the checkout is included except `tests/`, `install-flow.sh`, `install.sh`, plus the recursive cleanup of `__pycache__/`, `.agents/`, `.claude/`, `.codex/`, `.git/`, `*.pyc`, `.DS_Store`. New top-level files added in future versions are picked up automatically. The clone becomes disposable. Version is derived via `git describe` in the checkout, or via `FLOW_VERSION_OVERRIDE` if set.

Use this when:

- first installing `flow` directly from a clone (maintainer flow)
- moving the framework repo
- repairing the local launcher
- switching to release mode for a non-contributor install

After first install, `flow update` is the release update path. `flow install --release` and `flow install --develop <path>` are mode-conversion commands; they convert an existing install without re-running `install-flow.sh`.

## Maintainer Release Gate

A push to `main` first produces a credential-free semantic-release plan for the
exact pushed SHA. A no-release result is a green no-op. A release result must
pass the local candidate gate before the publisher receives a write token.

Pre-publication blockers are the full Python suite, generated-help drift,
release staging and transitive imports, tracked-tree cleanliness, candidate
fresh install and prior-version upgrade, machine and user setup, both runtime
sync checks, `flow doctor --check`, static runtime smoke, and a representative
CLI invocation. Evidence and per-check logs are retained as workflow artifacts.
`doctor --check --json` must report `ok: true` and zero errors. The isolated
runner permits only the named live-client manual-check warnings and empty local
telemetry warnings; every other doctor warning blocks publication. Static
runtime smoke remains a separate required check.

After publication, a read-only job verifies the tag and changelog-only release
commit, GitHub release and non-empty notes, public fresh install, and public
upgrade. A failure here means a release exists and needs a corrective commit;
it does not mean publication was prevented.

Live Claude/Codex command discovery, applied model and effort routing, external
identity, and actual provider grants remain manual. Never satisfy a failed gate
with `continue-on-error`, a force push, tag deletion, release deletion, or a
manual bypass.

If any release job fails, follow the [release failure runbook](release-runbook.md)
before retrying or changing remote state.
