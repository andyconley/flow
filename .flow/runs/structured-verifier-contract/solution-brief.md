# Solution Brief: Structured Verifier Contract

## Confirmed decisions

- New executions use protocol v8; v7 remains readable with unchanged meaning.
- `max_verifier_calls` is charter-configurable and defaults to two total calls.
- Flow permits at most one retry after the first valid fail or unusable verdict; the second outcome is terminal.
- Flow owns parsing, evaluation, evidence binding, counters, and terminal status.

## Design question

Compare at least two compatible placements for the Flow-owned verifier evaluation and retry/cap enforcement. Recommend exact contract boundaries, data flow, compatibility behavior, and independently mergeable chunks.

## Evidence inventory

- `.flow/runs/structured-verifier-contract/requirements.md`
- `.flow/runs/structured-verifier-contract/acceptance-criteria.md`
- `.flow/runs/structured-verifier-contract/research/architecture-review.md`
- `.flow/runs/shaper-delivery-runtime-contracts/archive.md`
- `cli/delivery_gateway.py`, `cli/execution_contracts.py`, `cli/execution_ledger.py`
- `tests/test_chartered_delivery_gateway.py`, `tests/test_magentic_execution_contract.py`
- Solution archive selection `4e49a8841f416609096c7ca5a0a5a7d3357207c0f938a1aaf6be6c4aee7e29c2` was unavailable because this worktree has no archive index.

## Boundaries

- No another Ollama feasibility proof.
- No semantic scoring, quorum, general retry engine, producer routing changes, historical recovery, nested subagents, or scheduler work.
