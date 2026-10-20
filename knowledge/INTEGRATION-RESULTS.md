# Isolated integration results — 2026-10-20

Implemented on `feat/managed-knowledge-pipeline` in a separate local clone. No push,
merge, release, Studio install change or MacBook operation was performed. The
starting commit was `659b265` (quota verification fix); the branch was subsequently
rebased onto `20b10c9`, including the two later quota fixes. The release checkout's
dirty work was never copied or edited.

## Verified behavior

The original six JSON-LD files in the current checkout match the POC's copied raw
corpus byte-for-byte. The shared Markdown seed contains all 21 cards, preserving
role, applicability, source arrays, manual prose and lossless originals. The
pre-existing JSON-LD role-rendering path is preserved; new shared updates use the
Markdown subcomponent. Consolidating the older role-rendering source is future
migration work, not a silent change in this branch.

A real CocoIndex 1.0.25 run used the existing local `qwen3:4b` model through an
isolated Ollama 0.32.1 process at 127.0.0.1:11435. Extraction took 84.43 seconds.
BM 0.23.2 then rebuilt the complete SQLite project with cached local
BAAI/bge-small-en-v1.5 embeddings. Audit: **21 notes, 21 authored FTS rows,
131 vector chunks, 37 directed typed edges, zero unresolved endpoints**, and all
physical vectors verified. Generated relationships are in each containing note;
the native BM graph is indexed from those notes. Search rows/chunks contain only
authored material. Fresh local inference can produce a different valid edge set
(the earlier POC had 36); do not treat generation identity as deterministic.

The five fixed questions were replayed through each actual native BM mode:

| Mode | Expected card ranks in question order | Hit@5 | MRR |
| --- | --- | --- | --- |
| Explicit default text | 2, 1, 1, 1, 1 | 5/5 | 0.9000 |
| Vector | 1, 1, 1, absent, 4 | 4/5 | 0.6500 |
| Hybrid | 1, 2, 3, 5, 3 | 5/5 | 0.4733 |

Vector and hybrid ranks exactly match the POC's original authored baseline.
The old POC's first arm used implicit hybrid over keyword queries; this test
really uses the configured text default, and its matching ranks are not proof
that the old arm was FTS. One vector miss remains; enrichment does not establish
an overall retrieval-quality gain. Native role filtering returned only the five
business analyst cards. Evergreen 2020 timestamps remained searchable; graph
traversal explicitly uses no timeframe filter.

The actual stdio MCP client listed and called `knowledge_status`, `search_cards`
and `traverse_cards`. Directed traversal returned real graph endpoints and
neighbor authored content. All 15 queries, role query, graph reads and MCP calls
left the published snapshot and local notes byte-for-byte unchanged. Repeated
processing with the same fingerprint did not create a generation.

A second real test used two copied cards and exercised six lifecycle events:
initial queued processing, adding a manual note, detecting an external manual
edit through the two-second reconciliation loop, removing a copied source and
cleaning all stale links, exposing a malformed-input failure while preserving
the prior snapshot, and rebuilding after simulated interrupted-run metadata plus
a corrected edit. The final audit had two notes, zero stale/unresolved edges,
fully verified vectors, and independent ZIP backups. The restart test simulates
an abandoned status record; it is not a power-loss test. Earlier development
also stopped a recorded private worker process; its confirmed failure published
nothing and a later clean build succeeded.

All **179 offline Flow regression tests pass** after the rebase, including **11 knowledge lifecycle tests**.

Lifecycle unit tests separately inject a mid-build edit, destructive whole-file
output, failed builds, manual edits inside generated blocks, shared/local update
conflicts, local deletions, symlinks, version/config changes, export/restore,
failed-fingerprint retry suppression, and command attachment.

## Evidence and reproduction

- `evidence/flow-integration-live.json`: raw 15-query responses, audit, graph,
  MCP checks and snapshot integrity assertions.
- `evidence/flow-integration-triggers.json`: real queue/watch/failure/recovery events.
- `evidence/knowledge-lifecycle.log`: targeted lifecycle tests.
- `evidence/flow-regression.log`: broader offline Flow tests.
- `verify_live.py` and `verify_triggers.py`: runnable live verification scripts.

From the repo root, with the separately provisioned pinned Python/cache and local
model, first configure an **isolated** home using the README commands. Then run:

```sh
/path/to/knowledge-python knowledge/verify_live.py --home /isolated/knowledge-home --output /tmp/flow-live.json
/path/to/knowledge-python knowledge/verify_triggers.py --home /new/isolated/trigger-home --python /path/to/knowledge-python --cache /local/fastembed_cache --output /tmp/flow-triggers.json
```

The trigger script intentionally requires a new home, edits/deletes only its
copied files, and currently expects the test model server at 127.0.0.1:11435.
The live script reads an already published generation. The tested invocation used
macOS `sandbox-exec` to deny every public outbound connection while allowing only
that loopback model port. It used no credentials or paid APIs.

## Limitations and recommendation

Review this branch before deployment. Dependency/model provisioning is explicit;
a fresh install seeds notes but reports pending until the separate local runtime,
cache and model are configured. Network fetch is implemented but the new remote
knowledge path does not exist until an approved publication; local-directory
fetch and its conflict semantics were tested. No GitHub fetch or publication was
performed for knowledge. The actual local MCP transport and parent Goose command
attachment were tested; a complete production provider/ACP agent job was not run.
The previous POC separately demonstrated real Goose parent/child retrieval.

Every changed corpus currently builds a fresh generation and re-extracts eligible
cards. This is simple and safe for 21 cards, but costs roughly 1–2 minutes; the
prior good snapshot stays usable. Queries copy a small database before invoking
native BM to protect generation immutability. Storage retention has no automatic
pruning yet. Ordinary process/file locks coordinate managed writers; an external
editor can still race a short fetch/restore write, so avoid concurrent manual
editing during those explicit maintenance commands. Published generation
immutability is enforced by the managed path, not OS access control against users
manually editing its files. Direct stock BM entrypoints bypass the private shim;
Flow agents get only the managed facade. BM upgrades require source re-audit.

Use this design for the small local corpus after review, keeping authored search
and inferred graph separate. Do not claim an accuracy improvement from more
links, auto-promote local knowledge, or release this larger integration before
reviewing its storage/provisioning tradeoffs.
