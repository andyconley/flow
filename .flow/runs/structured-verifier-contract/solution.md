# Solution: Protocol-v8 Structured Verifier Evaluation

## Problem

Flow needs a deterministic, evidence-bound verifier signal before handback. Provider completion must remain a factual observation, while Flow separately decides whether the verifier output is a valid pass, valid fail, or unusable. One retry is allowed inside a charter-controlled total-call cap.

## Applicable rules

- `scaffolds/default/standards/architecture.md` — keep provider normalization at the integration boundary and deterministic evaluation in Flow domain logic.
- ADR 0011 — Magentic coordinates; Flow owns grants, evidence, receipts, and reconciliation.
- ADR 0012 — observed responses and uncertain sends remain distinct.
- ADR 0014 — runtime execution is a projection of sealed Shaper and Delivery Charter authority.
- `scaffolds/default/standards/testing.md` — prove the contract with pure, ledger, gateway, replay, and compatibility tests rather than another provider smoke.

## Options considered

### A. Separate Flow evaluation records — selected

The provider returns ordinary candidate JSON. Flow durably observes and completes the provider action, then a pure evaluator creates a separately persisted evidence-bound evaluation. The ledger owns cap and retry eligibility, and receipts project both provider facts and Flow judgment.

- Advantages: truthful call status, replay-safe evaluation, transactional policy, explicit provenance, and durable retry behavior.
- Cost: additive tables, migration fixtures, and snapshot plumbing.
- Reversibility: medium; isolated to protocol v8 with v7 unchanged.

### B. Embed evaluation in provider results — rejected

The adapter or gateway adds parsed verdict fields to the provider result stored on the action.

- Advantages: fewer persistence changes.
- Costs: conflates provider fact with Flow judgment, complicates malformed-output observation, and weakens replay and receipt provenance.
- Reversibility: medium, with undesirable durable coupling.

### C. Let Magentic interpret the verdict — rejected

This violates the accepted ownership boundary because runtime coordination would become acceptance authority.

## Selected design

### Protocol and authority

- New chartered executions use protocol v8. V7 validators, fixtures, readers, and historical meaning remain unchanged.
- Add `max_verifier_calls` to Shaper intent, Delivery Charter, and the v8 envelope. Values are 1 or 2; default 2.
- A cap of 2 permits one initial call and one retry. A cap of 1 disables retry.

### Flow verifier contract

- Add a pure verifier contract/evaluator module.
- Candidate schema is closed and bounded: schema version, `pass` or `fail`, summary, and findings with `blocking` or `non_blocking` severity.
- Pass forbids blocking findings. Fail requires at least one blocking finding.
- Flow produces `valid_pass`, `valid_fail`, or `unusable` with a stable reason and bindings to action ID, verifier input, raw output, diff, and targeted-test evidence.
- Provider-supplied hashes are never trusted authority.

### Data flow

1. Flow persists the exact augmented verifier input before the provider send.
2. Flow grants and observes the provider call through the existing boundary.
3. A received provider result is recorded and the action completes before verdict parsing.
4. Flow evaluates and durably records the candidate output.
5. A valid pass may satisfy the verifier portion of handback.
6. The first valid fail or unusable evaluation is terminal for that action but retryable for the attempt when allowance remains. Magentic may propose the retry; Flow does not dispatch one itself.
7. A second non-pass, or the first when the cap is one, makes the attempt terminal failed. Transport uncertainty alone remains `unknown`.

This clarifies the approved requirements: “terminal fail” applies once no permitted retry remains; each provider action itself is terminal after its evaluation.

### Ledger and persistence

- Add append-only verifier-input and verifier-evaluation records keyed by action ID.
- Record exact replays idempotently and reject changed replay payloads.
- Enforce the verifier cap atomically inside the ledger decision transaction across every approved verifier identity.
- Count reservations and sends that can no longer be proven not dispatched; unknown calls consume allowance. Denials do not.
- Add named protocol helpers rather than extending scattered hard-coded protocol sets.

### Receipt and completion

- Protocol-v8 receipts include ordered evaluations and verifier usage with maximum, reserved/consumed, and denied counts.
- Receipt validation recomputes the counts and evidence links.
- Completed handback requires one exact `valid_pass` plus all existing producer, order, scope, test, authority, and receipt gates.

## Proposed chunks

1. **V8 contract and authority projection**: protocol helpers, pure evaluator, Shaper/Charter/envelope cap, compatibility fixtures, and ADR.
2. **Ledger enforcement and durable evaluation**: additive storage, atomic cap/retry decisions, idempotent records, snapshots, and concurrency tests.
3. **Gateway and receipt completion**: exact input persistence, observe-before-evaluate flow, Magentic retry signaling, terminal behavior, receipt projection, and acceptance tests.

## Owned risks

- SQLite migration drift — Owner: Flow maintainer. Mitigation: additive tables, old-ledger fixtures, and explicit v7 read tests.
- Magentic may stop rather than request the allowed retry — Owner: gateway integration. Mitigation: normalized retry-eligible response and deterministic supervisor tests for both stop and retry paths.
- Crash between response observation and evaluation — Owner: ledger implementation. Mitigation: durable response first and deterministic re-evaluation without provider resend.
- Strict output may expose more Ollama failures — Owner: verifier contract. Mitigation: stable unusable reasons and one bounded retry; prompt optimization remains separate.

## Artifacts

- New ADR: Flow-owned structured verifier evaluation and bounded retry.
- Protocol-v8 schema examples and a short pass/retry/terminal sequence in the implementation plan.

## Session model advice

- Coordinator recommendation: judgment, `gpt-5.6-sol`, high effort; the contract changes durable execution and receipt semantics.
- Active parent: unknown; no verified same-session identity was available.
- Effective delegated assignments: solution-architect and architect used judgment roles; test-engineer used the working role.
- Switch performed: no.

## Approval

- Accepted by the engineer on 2026-09-23.

## Next lane

- `flow-plan`, to shape the three selected chunks into an implementation-ready sequence.
