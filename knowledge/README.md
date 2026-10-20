# Flow knowledge subcomponent

This directory is versioned with Flow, independently of the Flow executable version.
`manifest.json` identifies a corpus revision and every authored card's SHA-256.
The first revision renders the 21 existing expertise cards without changing their
meaning, role, applicability or citations; each card retains lossless JSON-LD.
The original `scaffolds/default/expertise` remains unchanged for existing role rendering.
Future shared edits should update this Markdown corpus and its manifest in a reviewed PR.
Do not independently edit the lossless embedded original without reconciling its prose.

## Authority and paths

- Shared authored Markdown: `knowledge/cards/` plus `manifest.json` in this Git repo.
- Local authoritative authored Markdown: `~/.flow/v2/state/knowledge/notes/`.
- Local configuration, merge base, incoming conflicts, backups and exports: siblings
  of `notes/`, outside every replaceable release and virtual environment.
- Rebuildable enriched Markdown and Basic Memory databases: `generations/<id>/`.
  Each generated block lives in its containing card, not an edge sidecar. Authored
  local files stay free of generated text; generation copies are snapshots, not
  alternative editable notes. Search excludes generated blocks while the real BM
  relation table retains their typed directed edges.
- `CURRENT.json` selects the last audited generation with one atomic rename.
  Failed/interrupted builds never replace it. No garbage collection removes old
  generations or backups in this initial implementation.

`FLOW_KNOWLEDGE_HOME` can select an isolated test/data directory. Moving that
whole directory or its backup ZIPs does not require the Flow runtime. Models and
embedding caches must also be provisioned locally; they are not in Git.

## Supported local provisioning

Normal install and update detect and reuse healthy local knowledge assets. If assets
or configuration are missing, an interactive run prints the disk/network plan and
asks **download / defer / cancel** before acquisition. Download consent provisions
verified dependencies/embeddings, configures the extraction runtime and waits for
an audited initial snapshot before activating the new Flow runtime.

```sh
flow update                           # reuse assets, otherwise ask on a terminal
flow update --knowledge download      # dependency/embedding consent; model may ask
flow update --knowledge download --knowledge-model download --non-interactive # separate chat-weight consent
flow update --knowledge offline       # reuse verified installed assets; never acquire
flow update --knowledge defer         # deliberately install with knowledge deferred
flow update --non-interactive         # reuse healthy assets or fail without prompting
flow knowledge status
```

The same flags work with `install-flow.sh install` and the public `install.sh`
bootstrap. When piping bootstrap into Bash, consent uses an existing controlling terminal
(`/dev/tty`); it never reads the shell script as an answer. Without a terminal, pass
`bash -s -- --knowledge download --knowledge-model download --non-interactive`
for separate explicit dependency and model consent, or `--knowledge defer`.
Omit model-download consent to require an already provisioned extraction model. JSON and
`--non-interactive` runs never prompt; missing assets without explicit policy fail
before runtime activation. `--check` is metadata-only and does not provision.
A no-op update still completes deferred/missing knowledge provisioning.

**After this correction is released — transition from v0.52.0/v0.52.1:** v0.52.0 predates the integrated gate; v0.52.1 detaches the prompt worker from its terminal. These installed updaters cannot execute the corrected foreground prompt on their first upgrade. Use the current public bootstrap with an explicit
knowledge policy for this one transition; it uses the new installer over the existing
installation and preserves durable notes/configuration. An old `flow update` alone
cannot retroactively prompt/provision. Future updates use the integrated gate.

Explicit deferral reports `knowledge.state: deferred`, `ready: false`, the prior
snapshot (if any) and a resume command `flow update --knowledge download`.
Fresh deferred knowledge cannot serve agent tasks until provisioned; existing
known-good snapshots remain available. No fallback search is substituted.
Missing extraction chat weights cause a clear failure with exact Ollama commands;
Interactive install/update offers separate model download/defer/cancel consent.
Unattended chat-weight acquisition requires `--knowledge-model download` as well as
`--knowledge download`; otherwise satisfy the prerequisite manually or explicitly defer. Verified acquired assets remain cached.

Provisioning failures preserve the previous runtime, authored notes, settings and
snapshot. Backups include the mutable knowledge transaction; unexpected manual
edits/deletions remain active and are reported as preserved conflicts. Failed
attempts and acquired assets are retained for recovery. Rollback refuses to replace
knowledge changed since installation, including newly added configuration.
Uncertain cancellation retains process identities/audit evidence, skips restoration
and blocks further provisioning and agent launch until the recorded execution is
reconciled. It never blindly retries a possibly live writer. No active user
installation is touched by the tests.

`knowledge setup` remains the repair/advanced entrypoint:

```sh
flow knowledge setup                 # inspect the acquisition plan
flow knowledge setup --download      # explicit repair acquisition
flow knowledge doctor
```

`--knowledge download`, interactive install/update download selection, and advanced
`setup --download` are the acquisition consent boundaries. It acquires all
187 exact Python dependency pins from the official PyPI release APIs,
validates registry SHA-256/size, then installs offline with
`--require-hashes`. It acquires the FastEmbed-maintained Qdrant conversion of
BAAI/bge-small-en-v1.5 from the immutable Hugging Face revision in
`embedding.lock.json`, verifies every file's committed SHA-256/size, and eagerly
loads it with networking disabled. It never uses another registry or an unapproved source build.
Two exact legacy dependencies (pybars3 and PyMeta3) only publish source archives.
Only these sources, pinned by committed SHA-256, are built into wheels using four
pinned build-tool wheels inside a disposable macOS environment with all networking
denied. All other dependencies require compatible official binary wheels.
Source/build-tool pins are in `source-builds.lock.json` and
`build-requirements.lock`; resulting wheel/source receipts retain provenance. Progress includes each artifact name/size and validation
stage. HTTPS downloads use no user credentials or authenticated proxies.

Reserve at least **6 GiB free initially**, plus space for notes/backups/generations
and separately supplied Ollama weights. The reference macOS arm64 metadata resolution totals about 112 MB of main
dependency artifacts plus 3.2 MB of build tools; metadata adds some traffic.
Other platform/build selections can vary. Embedding files add 67,179,163 bytes
(about 67 MB). Verified completed profiles can be reused with 128 MiB free.
Python 3.12 is required; the managed Flow interpreter is selected by default.
`--python /path/to/python3.12` can select a matching architecture explicitly.
Advanced setup never acquires chat weights. Normal install/update can acquire only
the selected extraction model with separate explicit model consent. Existing setup selections are
preserved unless `--model` or `--ollama` is explicitly supplied.

Flow reuses an already running unauthenticated loopback Ollama server when the
requested extraction model is installed. The initial extraction default is
`qwen3:4b`. If unavailable, setup exits nonzero with `assets_ready: true`, retains
all verified assets and the prior configuration, and prints exact `ollama serve`
and `ollama pull` commands for the selected endpoint/model. Provision that model
explicitly, then rerun the same Flow setup command. Flow never starts Ollama, expands credentials, or changes the coding-agent provider/model.
Only a separately consented installer model pull changes the local model store;
Ollama retains resumable/shared downloads independently of runtime rollback;
failures or cancellation do not delete its cached model data.
The extraction model and the qualified ACP agent model (`gpt-oss:20b`) serve
different roles. Choosing extraction does not select the agent provider.

Once dependency/cache/model checks pass, setup backs up notes, configures a
versioned runtime/cache under `~/.flow/v2/state/knowledge/provisioning/<id>/`,
reconciles the shared corpus and automatically queues initial indexing. Wait for
`flow knowledge status` to show `ready`. Normal install/update waits for the audited snapshot before activation; advanced setup queues it. No manual wheel/cache assembly or `configure` command is needed for the online path. Published snapshots and
existing notes survive failed/interrupted acquisition. Partial downloads are
private and removed on failure; verified files are reused on explicit retry.
`--rebuild-runtime` creates a new isolated environment while retaining the old
one, for a failed or manually modified managed environment. Retention/pruning is
not automatic. Ordinary Flow commands never invoke acquisition.

### Offline transfer mode

On a connected machine, run the explicit online setup and transfer its verified
`provisioning/<id>/wheels/` and `embedding-cache/` folders. The wheel folder must
include `verified.json`; tampered/missing files or mismatched pins fail before
installation, without network fallback. A complete local Ollama model/server is
also required. On the offline machine:

```sh
flow knowledge setup --python /path/to/python3.12 --wheelhouse /media/flow/wheels
flow knowledge configure --python "$HOME/.flow/v2/state/knowledge/runtime/bin/python" --cache /media/flow/embedding-cache --model qwen3:4b --ollama http://127.0.0.1:11434
flow knowledge doctor
flow knowledge status
```

The offline environment is separate from Flow's runtime. Existing offline
`runtime/` directories are not overwritten; use a fresh isolated environment or
inspect/remove only a failed environment before retrying. Notes, backups and
exports remain intact. `doctor` accepts proposed `--python`, `--cache`, `--model`
and `--ollama` paths before configuration, reports failures separately and never
downloads. Status exposes the supported setup/diagnostics commands.

Basic Memory is 0.23.2 with audited Python source hashes; CocoIndex is 1.0.25
with local file targets and LMDB state. Inference workers strip credentials,
disable telemetry and force Hugging Face offline. Use an OS network sandbox for
a strict air gap: third-party telemetry configuration alone is not a universal
network-isolation guarantee. Online acquisition is intentionally separate from
subsequent local inference and retrieval.

## Updates and local edits

Install seeds the local store. Add/edit/delete commands enqueue processing:

```sh
flow knowledge write new-card.md --from-file /path/to/new-card.md
flow knowledge edit new-card.md --from-file /path/to/edited-card.md
flow knowledge delete new-card.md
flow knowledge fetch --ref main
flow knowledge fetch --from-directory /path/to/another/flow/knowledge
```

Network fetch reads only this repository's knowledge path through an anonymous
Git fetch, records the resolved commit, validates the manifest, and leaves Flow
binaries alone. Until this branch is reviewed and published, remote `main` will
not contain this new subcomponent; use `--from-directory` for isolated validation.
Three-way reconciliation replaces a local file only if it still matches the last
shared base. It preserves unpromoted edits **and local deletions**, records
conflicts in `base.json`, and saves incoming versions under `incoming/`. Resolve
conflicts by reviewing/copying the desired file, then fetch again. Local-only files
are preserved. Shared removals delete only locally unchanged cards.

Ordinary Flow workflow startup reconciles fingerprints; version, doctor and knowledge status commands are read-only inspections. Managed write/edit/delete/fetch/restore commands enqueue processing immediately. Standalone non-native query/graph reads reconcile too. The Flow supervisor checks every five seconds during a running job. Native ACP tool reads are read-only and delegate reconciliation to that supervisor; a standalone non-native MCP server polls every two seconds. For editing outside a running
Flow session, `flow knowledge watch` provides the same foreground reconciliation
loop; otherwise the next ordinary workflow startup or non-native query/graph read catches edits. There is no launchd,
watcher package, filesystem hook, database server or paid API. Pipeline code,
dependency lock, configuration, model digest and exact authored files participate
in the fingerprint. Generated snapshots and databases are outside its input tree,
so no self-trigger feedback loop occurs. A failed fingerprint is visible and is
not automatically retried repeatedly; fix the cause/edit input or explicitly run
`flow knowledge process`. Reads can keep using the prior successful snapshot.

Jobs serialize under a file lock. A crash releases that lock, and the next process
builds a fresh private generation; abandoned children can only affect their own
unpublished generation. Builds use bounded subprocesses and stop their process
groups on timeout. Staging is never reused after an uncertain outcome. A source
edit or code/config change during a build prevents publication. Every enrichment
attempt first ZIPs the working notes. Whole-file writers must pass exact authored
byte/inventory preservation and BM graph/projection audits before publication.

## Backup, export and promotion

```sh
flow knowledge export
flow knowledge restore /path/to/backups/123-before-enrichment.zip
```

Export creates an authored-only `cards/` and manifest under `exports/`, after a
backup. Promotion is deliberate: review the export's diff against `knowledge/`,
choose a corpus version, copy the approved files/manifest on a branch, test, commit
and open a PR. Export never stages, commits, pushes or publishes. Restore backs
up current notes first, validates the archive's flat Markdown paths, restores the
notes and enqueues a new generation; it does not restore a stale runtime or DB.

## Agent retrieval

The native Goose parent gets an absolute-path managed stdio extension; Summon children inherit it. ACP clients can filter custom environment variables, so the launcher receives the knowledge home explicitly and sets its own module path. Native worker sandbox grants are read-only for knowledge, code and model cache; query writes stay under per-run scratch. Local Codex ACP gets a separate loopback-only sandbox when its own config explicitly chooses a credential-free loopback model; mixed Claude profiles retain their existing permissions. Tools are `knowledge_status`, `search_cards` and `traverse_cards`. Keyword,
vector and hybrid search use the actual BM implementation through the pinned
projection shim. Search may specify an exact role. Graph traversal follows actual
`from_id`/`to_id` typed relations from the containing note and returns authored
neighbor text. No default recency filter excludes evergreen notes. Generation
selection is pinned per request; BM query initialization runs in a private temporary
copy so concurrent readers cannot mutate the published database. This trades some
latency/disk copying for a simple safe boundary. Legacy non-native sandboxed
experiments do not get a new knowledge extension/permission expansion.

Validation commands from `v2/`:

```sh
python -m unittest tests.test_knowledge -v
python -m unittest discover -s tests
```

The lifecycle tests use a deterministic builder for precise failure/race injection;
real CocoIndex/model/BM execution and retrieval evidence are documented separately
in `INTEGRATION-RESULTS.md`. A passing lifecycle unit test is not a live model run.

Coverage of all 13 roles is recorded in `COVERAGE.md`; the 21-card seed covers six roles, not every agent. Missing authoritative cards were not found or invented.

The read-only production ACP knowledge-use task passes with Codex ACP, local Ollama `gpt-oss:20b`, and the explicit namespace compatibility adapter. Enable it with `flow knowledge namespace-compat on` (disable with `off`); it requires an explicitly configured credential-free loopback Codex provider. See `NATIVE-ACP-RESULTS.md` for exact versions, evidence and reproduction. Qwen final-contract failures remain in `ACP-STATUS.md`. A complete code-changing implementation/review workflow and other provider/model combinations are not qualified. Merge/release still requires parent review.

If offline setup fails, its partial `runtime/` is retained and replacement is refused. Inspect/remove only that failed virtual environment, or provision another isolated environment and configure its Python. Notes, backups and exports must remain intact.

The native ACP transport remains explicit, as described in NATIVE-ACP-RESULTS.md.


### Rollback after knowledge use

`flow rollback` is deliberately conservative: any change to the recorded knowledge
inventory, including normal reconciliation/processing status, can make it refuse
with `Knowledge edits prevent rollback`. A same-version update does not clear that
guard. Refusal leaves the runtime, current knowledge and backups untouched; it is
not safe to delete the receipt or reset notes merely to force rollback.

Run `flow knowledge export` to preserve authored cards and the generated export
manifest; retain the durable knowledge directory/backups for configuration and
processing evidence. For a runtime downgrade after this refusal, use an explicit
published version, for example `flow install --version v0.52.0 --knowledge defer`.
This performs a fresh installation transaction around the current durable knowledge
rather than restoring the older knowledge backup. Deferral is visible and does not
provision missing assets. Select a compatible supported release and inspect
`flow knowledge status` afterward. There is no force-rollback flag.


Piped-bootstrap consent is read by the foreground installer from its controlling
terminal before the provisioning worker starts a new session. The worker receives
the selected dependency and separate model policies. Without a terminal, ask mode fails
without inferring approval; use an explicit noninteractive policy. This preserves
worker cancellation tracking without trying to read a terminal from a detached
process.


Install/update checks the selected local extraction model before acquiring missing
knowledge dependencies or embeddings. If it is absent or Ollama is unavailable,
the installer prints the exact selected model/endpoint and optional user-invoked
Ollama setup commands and a separate download/defer/cancel choice. It pulls no chat
weights without that separate approval. Explicit deferral remains available. The final summary names the currently selected Flow version on
both success and failure; a provisioning failure with an unchanged runtime pointer
means the previous Flow version remains active. Downloaded assets alone do not mean
runtime activation succeeded.


Known extraction identity/size evidence is stored in `extraction-models.json`.
The recorded `qwen3:4b` digest is 359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7,
matching the existing isolated extraction audit and the official catalog observed
2026-10-20. This is not a claim that all Qwen variants honor thinking-off or that
Qwen passed the coding-agent ACP final contract. Existing explicit local digest
selections win. Unexpected installed/acquired digest changes fail before dependency
acquisition; no alias/default is silently replaced. Unknown profile sizes are labeled
unknown; streamed Ollama progress reports exact layer totals when available.
