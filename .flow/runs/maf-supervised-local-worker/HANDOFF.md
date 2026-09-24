# Handback: supervised local MAF worker

## Scope

This run implements the approved first adoption slice for Microsoft Agent Framework/Magentic beneath Flow. Flow remains the owner of the run lifecycle, charter and manifest digests, action policy, one-use dispatch grants, provider invocation, execution ledger, and sealed receipt. MAF runs as an optional supervised child and may propose a bounded `test-engineer` action, but it cannot issue a grant or call a provider directly.

The slice deliberately covers one guarded local worker through the Flow CLI. Codex, Claude, MCP ingress, paid providers, automatic replay, delegated expansion, multi-turn recovery, and production release remain later slices.

## Implemented surface

- Versioned execution envelope, action, grant, result, and receipt validation in `cli/execution_contracts.py`.
- Run-local SQLite ledger with one-use grants, durable action status, denial records, aggregate delegation/concurrency limits, and fail-closed `unknown` handling in `cli/execution_ledger.py`.
- Flow gateway that validates the implementing run, manifest assignment, approved task and source digests, constructs the execution envelope, invokes the adapter, and seals the receipt in `cli/execution_gateway.py`.
- Optional supervised MAF child protocol in `cli/maf_supervisor.py` and `runtime/maf_runner/`. The child proposes work over bounded JSON-line stdio; only the Flow callback can authorize dispatch.
- Local Ollama adapter in `cli/local_worker.py`, constrained to loopback HTTP, exact model binding, response limits, no proxy use, and redirect rejection. Injected test transport is explicitly recorded as `local-stub`.
- CLI entry point: `flow run execute-local WORK_ID --assignment ID --task-file PATH [--json]`.
- Contract, ledger, gateway, adapter, supervisor, and CLI tests, plus README, CLI reference, scaffold help, architecture design, and ADR updates.

## Evidence captured

The primary post-snapshot physical local smoke completed successfully in attempt `44d98b9e0beb4d0d9a59c682b30af299`. Its receipt is at [`execution/44d98b9e0beb4d0d9a59c682b30af299/receipt.json`](execution/44d98b9e0beb4d0d9a59c682b30af299/receipt.json). An independent reviewer reconciled this receipt against the ledger, checkpoint, and all three source snapshots. Earlier independently reconciled evidence remains in attempt `48eacd2f33fa4b75839d26697481262f`.

- Provider: `ollama`; model: `llama3.1:8b`.
- `physical_call: true`; evidence: `flow_observed_local_http_response`.
- One Flow-recorded action completed with a one-use grant.
- Checkpoint: `985a0ac0-e16f-4be1-aa0e-203ecd656da9`.
- The receipt carries protocol revision 2 and explicit requirements and acceptance source paths with digests.
- Receipt, envelope, ledger, execution directory, and checkpoint permissions were inspected; files are owner-only and the directory is `0700`.
- The worker returned a basic arithmetic test containing `assert 2 + 2 == 4`; output and receipt digests matched.
- A missing optional MAF dependency was also exercised: the CLI produced a failed, no-dispatch receipt instead of silently bypassing the runtime boundary.
- Focused execution and supervisor tests passed: 25/25.
- Mutation checks caught and rejected a reused grant, a foreign attempt, and a changed receipt link.
- Follow-up focused coverage validates grant expiry, immutable source snapshots, checkpoint references, protocol expansion/identity boundaries, and receipt-link integrity.
- Local security review recorded in [`research/security-review.md`](research/security-review.md) found and rechecked fixes for file modes, partial-line timeout handling, proxy/redirect behavior, result provenance, and child exit handling.

The smoke demonstrates the end-to-end control path and receipt evidence. It does not establish specialist quality; the local model is a bounded execution test, not a quality benchmark.

## Handback checks

- The final post-change Flow suite passed 1,120 tests with one skip.
- Independent quality review approved the slice. `flow run verify` and orchestration handback validation passed.
- Claude and Codex user-level generated help were synced and both drift checks passed. Static runtime smoke found zero failures; four manual client checks remain for a fresh client session.

## Known limitations and next slice

The same-UID supervised child is a process boundary, not an OS sandbox. A receipt records Flow’s observation of the loopback HTTP response; it is not an independent attestation from Ollama. `unknown` attempts consume the bounded concurrency budget and require reconciliation; this slice does not implement automatic retry or crash recovery across multiple authorized calls. MAF checkpoint state remains linked evidence, while Flow’s ledger and receipt remain authoritative.

Next work should address multi-turn and restart/reconciliation behavior before adding Codex, Claude, MCP, or paid adapters. Paid providers stay disabled until enforceable per-call budgets and usage evidence exist.

## Reproduction

To reproduce, create or resume a revision-2 run in the `implementing` state with an approved local `test-engineer` assignment and a task artifact inside that run. The physical smoke used `local-task-hardening.txt` and the command documented by the CLI help and [`docs/cli-reference.md`](../../../docs/cli-reference.md). A local Ollama service with the exact `llama3.1:8b` model is required for a physical run; tests use the explicit local stub transport.
