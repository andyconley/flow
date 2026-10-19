# Usage, context and existing work

These commands observe the Goose/LangGraph runtime and preserved Flow records. They add no token/rate/usage gates or second coordinator. Existing exact-brief approval, execution deadlines and permissions still apply.

## Usage and context

```sh
flow --project /project metrics
flow --project /project --work work-id metrics sessions
flow --project /project metrics context
flow metrics sessions --all --limit 25
flow cost summary --all --json
flow cost active --json
flow harvest claude
flow harvest codex
flow normalize
```

`metrics` and work `status` read Goose's session snapshots and usage ledger: provider/model, observed role where its recipe identifies it, parent/child lineage, token classes, reported/estimated cost, coverage and Goose compactions. Sessions count once; snapshots reconcile with their own ledger instead of being added to it. Generic workers retain an unknown role. Missing telemetry stays null with coverage diagnostics. Reported cost is never labeled an actual subscription bill.

Job attempts capture launch context configuration and session lineage. The existing process supervisor refreshes these observations during execution and emits an informational local-context warning once per observed session near its window. Observation failure never changes execution outcome, approval, retry allocation or provider choice.

`cost`, `harvest`, `normalize`, `plugin-usage`, and read-only `model context/resolve` reuse existing reporting modules from the canonical checkout. Native transcript history can overlap Goose observations; these views are labeled separately and their totals are not blindly combined. Harvest/normalization update the existing reporting store when explicitly invoked or through existing on-demand report behavior.

Context comes from user device settings (`~/.flow/user/flow.toml`, `[local_machine]`), user provider profiles (`~/.flow/user/runtime.toml`), and project provider overrides (`.flow/runtime.toml`). Positive explicit `GOOSE_INPUT_LIMIT` wins. Otherwise a matching local model profile, shared unambiguous local window, or explicit device context is used. Without one, the provider/model default remains. Conflicting/malformed settings are reported; there is no arbitrary 8K fallback, automatic capacity clamp or usage gate.

Goose's Ollama provider maps `GOOSE_INPUT_LIMIT` to `num_ctx` and its context resolver. Local output/compaction settings can also apply when the coordinator is Ollama. Native Codex/Claude context and compaction remain native-client-owned. No unsupported recipe field or fabricated native occupancy is injected. Last reported local request size versus a declared window is labeled accordingly, not presented as live/historical allocation. Goose compaction events and native compaction history have different visibility.

Flow-owned global native hooks removed by the original cutover are not automatically reinstalled. Native history/context reports work on demand via `cost active/verdict/warn`; unrelated user hooks remain user-owned. Worker hooks remain isolated as before. Inspecting these views needs no provider test or login.

## Runs and handoff

```sh
flow --project /project runs
flow --project /project --work old-id status --legacy
flow --project /project run list --json
flow --project /project --work successor create --legacy-run old-id --request 'Inspect and define successor scope'
```

`runs` separates v2 checkpoints from historical `.flow/runs` in the project and ancestor overlays. `status --legacy` is explicit read access. The compatibility `run` bridge permits only list/status/history, never execution or transitions.

Legacy SDK/native checkpoints are not LangGraph checkpoints. Continue a legacy active run through its original runtime, or use a distinct new v2 ID with `create --legacy-run`. The successor records the original path/digest as provenance, imports no approval, and waits for a new brief and exact-revision approval. Originals are unchanged. Legacy process quiescence is explicitly unobserved: establish it through the original runtime and inspect partial effects before approving a successor in the same workspace. Creating a successor neither stops the old process nor permits overlapping coordinators. A reference does not establish completion or current authority.

V2 immutable briefs, contexts, assignments, results and closures remain at `<project>/.glg/work/<id>/`. Source-local checkpoints remain at `v2/artifacts/glg-state/<project-key>/<id>/workflow.sqlite`; retain them when rebinding installations. `.glg/INDEX.md` is a rebuildable closure projection, not workflow authority.

## Archives, backlog and registry files

```sh
flow --project /project archive list
flow --project /project archive search 'decision' --limit 10
flow --project /project archive legacy-search 'decision' --json
flow --project /project archive legacy-inspect SOURCE_UUID:work-id --json
flow --project /project archive import-preview old-id --json
flow --project /project backlog list
flow --project /project backlog --file docs/backlog.md
flow gaps list --json
flow projects --file /path/to/existing-registry.json
```

Archive list/search inspect v2 closures and preserved legacy abstracts with explicit origin/provenance. Historical documents are not silently qualified as current approvals. Responses are bounded; originals remain at returned paths. `legacy-*` views reuse existing qualified/ranked retrieval and preserve its validity, source-identity and availability diagnostics. No automatic import, mutation, identity generation or legacy-run migration occurs. The native archive skill can inspect these views while keeping closure and user acceptance separate.

`backlog` reads existing project backlog files and explicit closure follow-ups without changing order. Edit a chosen project file through approved host file tools. Existing `gaps add/list/promote` remain available for the personal capability-gap ledger/framework backlog, with original provenance/promotion rules. Promotion keeps the existing legacy framework-source target; it is not silently retargeted to the v2 install. No automatic promotion occurs.

No universal legacy Flow project-registry contract was established by this port. `projects` can inspect recognized existing Flow registry files or explicit `--file` without writing or claiming migration. Native application project lists remain app-owned. This is read access, not an invented replacement registry or registration service.
