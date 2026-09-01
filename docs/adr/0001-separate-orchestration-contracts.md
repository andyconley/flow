# ADR 0001: Separate Orchestration Contracts from Lifecycle State

- Status: accepted
- Date: 2026-09-01

## Context

Flow's C-lite protocol uses `run.json` as a small current-state projection and `events.jsonl` as transition history. Delegation briefs, capability evidence, claim provenance, shared-mutation records, and verifier identity are more detailed and evolve independently from lifecycle state.

## Decision

Keep `run.json` at schema version 1 and add an additive `protocol_revision`. Revision-2 runs reference a versioned `.flow/runs/<work-id>/orchestration.json` contract. A read-only validator checks that contract at dispatch, handback, and acceptance; `cli/runstate.py` calls it before gated lifecycle writes.

## Consequences

- Existing runs without a protocol revision retain revision-1 behavior.
- The orchestration schema can evolve without turning the lifecycle projection into a workflow database.
- Explicit validation and lifecycle gates share one implementation.
- Structural checks cannot prove hidden runtime permissions, semantic truth, or external transactional behavior; the documentation and diagnostics state those limits.
- Validation refusal is atomic with respect to lifecycle files. The pre-existing filesystem failure window between writing the projection and appending history remains detectable by `flow run verify` and is not redesigned here.

## Rejected alternatives

- A new orchestration lane or command would duplicate existing lifecycle semantics.
- Embedding detailed assignments in `run.json` would couple two change rates and strand older runs.
- Runtime-specific validators would split policy between Claude and Codex.
