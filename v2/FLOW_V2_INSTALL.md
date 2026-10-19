# Flow v2.0 installation and command guide

Flow v2.0 is the product name. Goose/LangGraph is its engine. `poc.glg`, `.glg/` artifact directories and older `GLG_*.md` filenames remain compatibility/internal names; renaming the product does not rewrite existing work history. The local version is 2.0.0-preview.

## Reproducible source preparation

From the canonical Flow repository root, use Python 3.12+ and Node/npm already installed on the host:

```sh
./install-flow-v2.sh prepare
./install-flow-v2.sh install --dry-run
./install-flow-v2.sh install
```

Preparation installs locked Python/npm dependencies. On Apple Silicon macOS it automatically verifies and extracts the bundled patched Goose executable; Rust and a separate extraction command are unnecessary. Install/update also extract a missing bundled executable, including when invoked through an existing v2 launcher. Reruns verify and reuse it; dry runs validate the archive and report planned extraction without writing. Modified or incompatible extracted binaries are rejected and preserved. On other platforms, use `prepare --build-goose` with a Rust toolchain to build the official pinned Goose base plus the shipped patch. It never downloads a model or signs into an account. The source and patch digest/build features are recorded in `vendor/goose.lock.json`; see `vendor/README.md`. Existing native Claude/Codex authentication remains client-owned. Native sandbox execution currently targets macOS; Linux CI exercises offline contracts and installation fixtures without user accounts.

For an existing matching Goose build, set `FLOW_V2_GOOSE_BINARY` to its absolute path. Node discovery uses PATH or `FLOW_V2_NODE`. The v2 source is the repository's `v2/` directory; all generated dependencies, logs and account references stay in its ignored local runtime directories. The bundled executable and its build provenance are distributed; machine-specific runtime state and credentials are not.

## Existing-Mac installation

This installer binds to this source checkout, its existing `.venv`, the verified bundled Goose executable, a source build under runtime/goose, or the explicit FLOW_V2_GOOSE_BINARY path and the existing role bundle. It does not download dependencies, create credentials, install a daemon, change security permissions or contact providers. Moving/removing the checkout breaks that binding; rerun with `--source /new/checkout` after the matching local runtime is available. Updates refresh the selected source; they do not fetch remote code or build dependencies automatically.

From the source checkout:

```sh
.venv/bin/python -m poc.install install --dry-run
.venv/bin/python -m poc.install install
```

Default side-by-side surfaces:

| Path | Purpose |
|---|---|
| `~/.local/bin/flow-v2` | Source-bound launcher and install/update/inventory/select/restore entry |
| `~/.agents/skills/flow-v2/SKILL.md` | Codex opt-in entry; loads the requested private v2 command body |
| `~/.claude/skills/flow-v2/SKILL.md` | Claude opt-in entry |
| `~/.flow-v2/skills/flow-*/SKILL.md` | 14 staged v2 command bodies, one shared catalog |
| `~/.flow-v2/install.json` | Install ownership/source/selection record; not workflow state |

Use `$flow-v2` in Codex or `/flow-v2` in Claude, then request boot/define/plan/etc. Refresh native-host skill discovery or open a new session if the entry is not listed. Until explicit cutover, global `flow-*` skills still mean the legacy installation. No `glg-*` aliases are generated.

## Familiar command meanings

For shell work-item actions below, use `flow-v2 --project PROJECT --work ID SUBCOMMAND`. Context uses only `--project`. After explicit activation, `flow` is an equivalent launcher.

| Native skill | v2 behavior / shell mapping |
|---|---|
| `flow-boot` | Read-only `context`: project instructions, Git identity, recorded work and next action. No run/model created just to orient. |
| `flow-define` | `create --request …`; useful `assign --stage define --question …`; actual native-host research/delegation; `stage --stage define --file …`. |
| `flow-solution` | Optional `assign/stage --stage solution`; `approve-stage --stage solution` is approach-only authority. |
| `flow-plan` | Host Delivery Lead synthesizes useful expertise; `assign/stage --stage plan`, then canonical `brief --file …`. |
| `flow-implement` | `approve --actor … --revision …` for an actually authorized exact brief. Starts the existing implementation/check/fresh-review graph. |
| `flow-review` | Fresh review is automatic during delivery; inspect actual evidence. Explicit `resume --decision-file …` with action=retry-review can recover a blocked review of an unchanged candidate within its original deadline. No standalone review engine. |
| `flow-status` | `status` for one item, or `context` for project orientation. LangGraph is authority. |
| `flow-resume` | `resume`, optionally with an actual decision file. Preserve operation identity, typed permission/scope pauses and uncertain-effect inspection. |
| `flow-close` | Inspect automatic closure and optionally `index`. Do not silently accept, publish or deploy. |
| `flow-archive` | Closure inspection plus explicit legacy archive read views; no automatic memory/gap disposition. |
| `flow-accept` | Separate user-requested `accept --actor … --revision …` for a reviewed-and-ready closure. |
| `flow-scout` | Small clear task via `create --brief-file …`, followed by actual exact-revision approval and normal checks/review. |
| `flow-init-project` | Host reads `context`, reuses project instructions, and may write an agreed `.glg/PROJECT.md` using native file tools. No old framework scaffolding CLI is invoked. |
| `flow-help` | Catalog, architecture/role guidance, `--help`, `--version` and this guide. |

These are native-host instructions over real CLI contracts. `assign` records an assignment and `stage` imports actual findings; neither pretends to have executed research. The 13 role recipes remain available to Goose. Native hosts can load role expertise from the source role bundle and use their supported delegation mechanism rather than assuming that old global agent registrations exist after cleanup.

Shaping, approach decisions and planning do not authorize implementation. Final approval binds the current brief. Reviewed-and-ready is technical completion; acceptance is separate. Closure does not authorize commit/merge/push/deploy. Unsupported old behaviors include automatic migration of historical SDK sessions, duplicate MAF/OpenHands coordinators, orchestration-manifest ceremonies, token/rate gates, a second lifecycle ledger, global install-on-boot and automatic native session restoration.

## Update and explicit cutover

```sh
flow-v2 update --dry-run
flow-v2 update
flow-v2 inventory
flow-v2 activate --replace-legacy --dry-run
```

`inventory` is read-only. It reports attributable removals, selective shared-config edits, ambiguous ownership and retained dependencies. Review that concrete inventory before explicitly selecting replacement:

```sh
flow-v2 activate --replace-legacy
```

Activation replaces `~/.local/bin/flow` and supported `flow-*` skills in `~/.agents/skills` and `~/.claude/skills`. One v2 catalog supplies both clients; the opt-in `flow-v2` entry remains useful but is not a duplicate command set. Old native-host `flow-*` commands/prompts/skills, hook scripts and agent definitions are cleaned only when a valid Flow ownership manifest and matching hash/link establish ownership. Known legacy Flow wrappers are recognized narrowly. Unmanifested or edited active command/config collisions block selection with the exact path. Other ambiguous legacy files remain listed for manual review.

Ambiguous links also protect their generated targets: a file is not removed merely because it has a matching ownership hash when a retained ambiguous link still depends on it. Retained ambiguity and target information persists in the installation record/backup after old manifests are removed.

Shared JSON settings keep unrelated keys, handlers and permission values. Only hooks that reference confirmed owned script paths are removed. Codex's marked Flow role block is removed only when its ownership hash and surrounding TOML validate, preserving outside text/settings. Modified shared config is retained and reported. This installer does not remove credential/account stores or project paths. Dormant `.flow/source`, user overlays and runtimes/backups are retained: current role composition still depends on source, and historical tools/data may be needed. They are not active v2 registrations; bulk disk purging is deliberately unsupported.

Before replacement, each affected original file/directory/symlink is backed up beneath `~/.flow-v2/backups/<selection-id>/`, with a snapshot map. Skill directory symlinks are replaced rather than written through. An activation write failure restores the original legacy surfaces. Repeat install/update/select is idempotent and does not create nested legacy backups or duplicate registrations.

## Rollback

```sh
flow-v2 restore --dry-run
flow-v2 restore
```

Restore puts back the exact legacy launcher, skills, hooks, manifests and shared configuration from the selection snapshot, removes newly introduced replacement skill paths that were originally absent, and leaves the opt-in v2 launcher/catalog available. It also retains the outgoing v2 surfaces in the backup. If shared configuration has been independently edited since selection, rollback stops before making changes and names the file/backup for reconciliation; it never silently overwrites those edits. Installing/updating an opt-in surface that the user modified likewise stops rather than overwriting it.

Use `--home /disposable/target` on installer actions for an isolated fixture. It does not mean that target is auto-discovered by a running native app. The connected Mac installation validates files/launcher and pre-approval CLI behavior; native UI discovery may require refresh/new session. No provider inference is needed for packaging smoke tests.

## Current limitations

The installer binds to a prepared source-local runtime. Explicit preparation installs locked Python/npm dependencies and optionally builds pinned Goose when host toolchains are available; selection/update does not fetch remote code. It is not a multiuser service, deployment or old-run migration tool. Source composition still references Flow's retained content resolver. Existing approved live scenario and focused error propagation evidence remain valid; this packaging change does not launch another vendor/role qualification campaign.

## Informational reports and existing work

See [operations and observability](FLOW_V2_OPERATIONS.md) for `metrics`, native `cost`/harvest reports, device context settings, explicit legacy `runs`/status/handoff, archive inspection, backlog/gap access, and registry-file reads. Unknown provider telemetry remains unknown. These views add no token/rate/usage gates and do not resume legacy checkpoints as v2.
