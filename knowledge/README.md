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

## Isolated dependency setup

Knowledge has a separate Python 3.12 environment, not the Flow runtime environment.
Exact resolved pins are in `requirements.lock`; BM 0.23.2 source hashes are checked
before any BM operation. The private search projection shim requires re-audit
before changing that version or source distribution. CocoIndex is 1.0.25, using
local file targets and LMDB state, with no Neo4j or PostgreSQL service.

Prepare a wheelhouse explicitly from the official registry (or transfer an already
verified wheelhouse for an offline machine):

```sh
python3.12 -m pip download --index-url https://pypi.org/simple --only-binary=:all: --no-deps -r knowledge/requirements.lock -d /path/to/knowledge-wheels
flow knowledge setup --python /path/to/python3.12 --wheelhouse /path/to/knowledge-wheels
flow knowledge configure --python "$HOME/.flow/v2/state/knowledge/runtime/bin/python" --cache /path/to/preprovisioned/fastembed_cache --model qwen3:4b --ollama http://127.0.0.1:11434
flow knowledge process
flow knowledge status
```

The embedding cache must contain BAAI/bge-small-en-v1.5 (384 dimensions). The
Ollama model must already be installed locally. Configure records its digest and
reconciliation detects changes to that tag. Only unauthenticated loopback Ollama
is accepted; inference workers strip credential variables, disable telemetry,
and force Hugging Face offline. No dependency or model downloads occur during
agent launch. Wheel pins are exact but this lock has no wheel hashes; verify a
transferred wheelhouse's provenance yourself. The POC's observed pre-disable
telemetry uncertainty is not evidence that every third-party library is universally
air-gapped: use an OS network sandbox for a strict offline deployment/test.

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

Each Flow startup and each agent tool read reconciles fingerprints. The tool server
also checks every two seconds while it is alive. For editing outside a running
Flow session, `flow knowledge watch` provides the same foreground reconciliation
loop; otherwise the next Flow command/read catches edits. There is no launchd,
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

The native Goose parent gets the managed stdio extension; Summon children inherit
it. Tools are `knowledge_status`, `search_cards` and `traverse_cards`. Keyword,
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
