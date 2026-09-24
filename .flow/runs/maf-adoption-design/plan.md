# Draft plan: first supervised MAF execution slice

Status: approved by Andy on 2026-09-19. User confirmed the target: first foundation/contract slice, ending in one physical local guarded worker started from the Flow CLI. Codex, Claude, and MCP are later slices. This plan follows [ADR 0011](../../../docs/adr/0011-supervise-maf-behind-flow-gateway.md) and [the adoption design](../../../docs/maf-adoption-design.md). Implementation has not started.

## Problem and outcome

Flow has approved MAF as a supervised, replaceable execution runtime but has no production gateway, execution record, or CLI path that proves one worker call can cross Flow policy. Andy and Flow operators need to start an existing approved run, get one local specialist result, and inspect what Flow authorized and observed. Success is a complete attempt/decision/result/receipt trail with zero worker calls on denial or uncertainty, while the base CLI remains usable without MAF installed.

## Scope and decisions

- **Entry:** propose `flow run execute-local <work-id> --assignment <id> --task-file <path>`. Require the existing run to be `implementing`, its revision-2 orchestration manifest to validate at dispatch, an allowlisted `test-engineer` assignment, and an approved requirements/acceptance snapshot. The task file must be a bounded Flow-controlled run artifact, not an arbitrary path. Exact spelling may be adjusted only to match CLI conventions during implementation; behavior is fixed here.
- **Charter source:** hash the approved requirements, acceptance criteria, assignment and execution envelope. Call this a charter **snapshot**, not a completed Shaper charter implementation. Include source paths, digests, and revision in the attempt. Do not infer delegated Shaper approval from it.
- **Provider:** one locally configured Ollama model through a Flow-owned adapter. A deterministic `local-stub` adapter is for contract/integration tests and must be labeled as such. No paid route can dispatch. The effective `test-engineer` definition comes from the framework/user-overlay source merge, is snapshotted by digest, and is supplied to the guarded participant with the bounded task.
- **Execution shape:** Flow CLI/application service creates a run-local execution attempt and immutable envelope. It starts an optional MAF child process with a fixed argv and a versioned, bounded line-delimited JSON stdio protocol. The child may instantiate only the Flow-supplied guarded executor factory from that envelope; it has no raw-participant input path or provider credentials. It proposes one action. Flow validates and durably records the action, policy decision and one-use grant, then calls the local adapter. It returns a normalized result to MAF. The child reports a checkpoint reference and final synthesis; Flow verifies the ledger and seals the receipt outside worker write scope. Child output never advances C-Lite lifecycle state.
- **Policy:** Flow owns specialist/provider allowlists, six delegations, three concurrent, two replans, paid budget zero for this slice, time/output limits, and deny reasons. This slice consumes one delegation and zero replans, but the ledger must reject duplicate/reused grants and enforce the full envelope deterministically. Grant and adapter invocation live in the Flow parent so a child cannot call the provider directly through Flow's application path.
- **Failure:** no automatic retry. A launch failure or pre-dispatch denial leaves a failed/denied attempt with zero calls and a sealed terminal receipt recording no dispatch and the failure category. If Flow has recorded a physical dispatch but cannot establish completion after child or adapter failure, record `unknown` and require reconciliation. A completed local result may be incorporated into a receipt; it does not mark the run `handback_ready` automatically.

Out of scope: parallel or repeated workers, restart/resume of an in-progress MAF workflow, Flow-gated live replans, Codex/Claude adapters, paid-budget enablement, Shaper expansion decisions, MCP, broad specialist migration, Git commit-bound code handback, and a Flow-native scheduler/checkpoint engine. Preserve stable IDs and checkpoint references for the next recovery slice.

## Contracts and persistence

| Record | Required meaning |
| --- | --- |
| Envelope | Schema version, run/attempt IDs, approved source digests, assignment and definition digests, allowed role/instance/provider/model, hard limits, timeout/output cap. Immutable after child start. |
| Action request | Stable action ID bound to attempt, envelope, role, instance, task digest and sequence; MAF proposal has no dispatch authority. |
| Decision/grant | Flow-committed allow/deny reason; allowed grant binds exact action/provider/model/task, expires, and is consumed once. No grant on denial. |
| Observed result | Flow-observed physical call status, provider/session metadata when available, bounded output hash/reference, error category, start/end times; missing usage is unknown, not zero. |
| Receipt | Flow-sealed link to envelope, action, decision, grant, checkpoint reference or explicit absence, observed result and artifact hashes; marks stub vs physical call honestly. |

Store execution records below `.flow/runs/<work-id>/` behind a Flow-owned storage module; do not change `run.json` schema or use lifecycle `events.jsonl` as a dispatch ledger. Use a transactional ledger for decisions and one-use grant consumption. Reject unsupported protocol/schema versions, mismatched digests and IDs, oversized messages, unsafe paths, and changed definitions. MAF checkpoint state is a linked execution reference, never a policy grant.

## Implementation order

1. Add stdlib-only contract and identity modules plus serialization/validation tests. Define record versioning, canonical digests, exact state enums and path bounds. Keep MAF imports out of these modules.
2. Add the Flow-owned run-local ledger and deterministic policy gate. Make action identity immutable, decisions transactional, grants one-use, and unknown state fail closed. Test competing requests and every hard cap.
3. Add effective specialist resolution, gateway, and a local adapter. Snapshot the selected definition, reject raw participant input and disallowed assignment/provider/model before adapter invocation. Add a fake transport for tests.
4. Add optional supervised MAF runner and Flow parent stdio protocol. Parent alone opens the ledger and invokes the local adapter; child only proposes work and coordinates. Pin tested MAF packages in an opt-in install. Test crash, EOF, invalid message and timeout paths.
5. Wire CLI command, receipt readback, `--help`/README/operator docs, and an isolated run fixture. Run a real local Ollama smoke with one bounded `test-engineer` task and independently inspect the receipt. Do not use paid providers.

Likely modules: `cli/execution_contracts.py`, `cli/execution_ledger.py`, `cli/execution_gateway.py`, `cli/maf_supervisor.py`, `cli/local_worker.py`, optional `runtime/maf_runner/`, CLI parser/dispatch in `cli/flow.py`, and focused tests. This is a suggested structure; helpers may be combined if one boundary remains clear. `cli/runstate.py` remains the lifecycle writer and `cli/orchestration.py` remains structural validation.

## Acceptance and review

- Base CLI and contract tests pass when the optional MAF runtime is absent; missing runtime yields a specific diagnostic for `execute-local`.
- Automated CLI integration uses `local-stub` and proves the full control/receipt path without a model server. Separately, a required opt-in acceptance smoke launches the same CLI path with the optional child, obtains one Flow grant, invokes one physical local Ollama worker, and yields a receipt whose hashes and IDs match independently read ledger and source files. If Ollama is unavailable, record `runtime_unavailable`; the physical-worker criterion remains open.
- Denied role/provider/model, raw participant, altered envelope, duplicate action/grant, malformed protocol, timeout, and child failure make no additional adapter calls. Post-dispatch uncertainty becomes `unknown` and cannot retry automatically.
- Lifecycle files change only through existing transitions. No worker/child writes policy or receipt artifacts. A test double is labeled `local-stub` and cannot stand in for the physical-call acceptance result.
- Review checks the dispatch boundary, cost posture, receipt claims, install isolation and recovery semantics; run the Flow unit suite, fresh optional install/CLI smoke, `flow run verify`, orchestration validation and `git diff --check`.

## Next lane

`flow-implement` after this plan is accepted and `approve-plan` succeeds. The work spans contracts, persistence, subprocess integration and runtime evidence; a scout would not give enough review or recovery structure.
