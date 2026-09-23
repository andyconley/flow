# Plan: Protocol-v8 Structured Verifier Evaluation

## Problem statement

Flow currently proves that a distinct verifier provider call occurred after a scoped producer edit and passing targeted test, but provider prose is not an enforceable acceptance signal. Protocol v8 must separate the observed provider response from Flow's structured evaluation, permit one Magentic-proposed retry within a sealed total-call cap, and preserve v7 meaning and readability.

## Desired outcome

New chartered jobs use protocol v8. Successful handback requires a Flow-owned `valid_pass` evaluation bound to the exact verifier action, supplied input, raw output, observed diff, and targeted-test evidence. A first non-pass may be retried once when the Charter allows two calls; the second non-pass is terminal. Flow never silently dispatches the retry.

## Scope

### In scope

- Protocol v8 and named protocol capability helpers.
- Shaper Contract v2 and Delivery Charter v2 for new runs, with v1 readers retained.
- Closed verifier candidate and Flow evaluation schemas.
- `max_verifier_calls` projection and validation, default 2 and permitted 1–2.
- Additive verifier-input and verifier-evaluation persistence.
- Atomic verifier reservation, cap accounting, retry eligibility, and replay conflict detection.
- Gateway observe-before-evaluate flow and Magentic retry signaling.
- Protocol-v8 receipt projection, terminal validation, inspection, and deterministic tests.
- Frozen v7 receipt/envelope and pre-v8 SQLite compatibility fixtures.
- ADR 0015 documenting Flow-owned evaluation and bounded retry.

### Out of scope

- Another Ollama availability or semantic-quality smoke test.
- Prompt tuning, semantic scoring, quorum, or multi-verifier voting.
- General retry machinery, producer routing changes, historical attempt reconciliation, nested subagents, or scheduler work.
- Changes to v6 inspection-only behavior or v7 historical semantics.

## Workflow states and invariants

1. **Pre-evidence denial**: verifier proposed before a Flow-observed edit and passing targeted test; deny before send and consume no verifier allowance.
2. **Reserved**: ledger atomically grants a verifier proposal within both global limits and `max_verifier_calls`.
3. **Send claimed**: exact augmented verifier input is durably bound to the action and the adapter send boundary is recorded. The call consumes allowance.
4. **Unknown**: transport outcome is uncertain. Preserve `unknown`, consume allowance, and never reinterpret it as unusable output.
5. **Response observed**: a returned provider response is durably recorded and the provider action completes before Flow parses its verdict.
6. **Evaluated pass**: Flow records `valid_pass`; existing completion gates may proceed.
7. **Evaluated non-pass, retry eligible**: first `valid_fail` or `unusable` with remaining allowance. Return a normalized result to Magentic; only Magentic may propose the retry.
8. **Terminal failed**: no allowance remains, Magentic stops without a pass, or the second evaluation is non-pass.
9. **Cap denied**: excess proposal is denied before adapter invocation and is reported separately from consumed calls.

## Contract expectations

### Candidate verdict

- Exact bounded object: `schema_version`, `decision`, `summary`, and `findings`.
- `decision`: `pass` or `fail`.
- Finding: exact bounded `severity`, `summary`, and `evidence`; severity is `blocking` or `non_blocking`.
- Pass forbids blocking findings. Fail requires at least one blocking finding.
- Provider output supplies no trusted evidence hashes.

### Flow evaluation

- Disposition: `valid_pass`, `valid_fail`, or `unusable` with a stable reason.
- Bindings: action ID, verifier-input digest, raw-output digest, diff digest, and targeted-test evidence digest.
- Exact replay is idempotent. Changed replay payload or binding is rejected.

### Verifier usage

- `maximum`: sealed `max_verifier_calls`.
- `reserved`: verifier grants that have not been proven not dispatched.
- `consumed`: calls whose adapter send boundary was crossed, including unknown outcomes.
- `denied`: verifier proposals rejected by cap or retry state.
- Receipt values are derived from ledger state, never caller supplied.

### Compatibility

- Protocol v8 and contract v2 apply only to new chartered executions after chunk 3 cutover.
- Protocol v7 validation and receipt meaning remain unchanged and readable.
- SQLite changes are additive; existing rows are never rewritten.
- V6 remains inspection-only.

## Implementation chunks

### Chunk 1: Contracts and compatibility

Files/modules:

- New `cli/verifier_contracts.py`.
- `cli/delivery_contracts.py`, `cli/delivery_control.py`, `cli/execution_contracts.py`.
- Protocol helpers and v1/v2 contract readers/builders.
- `docs/adr/0015-flow-owned-structured-verifier-evaluation.md`.
- New evaluator and compatibility fixtures/tests.

Work:

- Define candidate/evaluation schemas, bounds, reason codes, canonicalization, validation, and digesting.
- Add protocol v8 and named helpers for Magentic, chartered delivery, and structured verification capabilities.
- Add `max_verifier_calls` to v2 Shaper/Charter/envelope contracts.
- Leave active execution construction on v7 until chunk 3.

Gate:

- Pure evaluator and contract tests pass.
- Frozen v7 envelope/receipt validate unchanged.
- Full suite passes with v8 dormant.

### Chunk 2: Ledger authority and migration

Files/modules:

- `cli/execution_ledger.py` and focused ledger tests/fixtures.
- Extend `tests/test_magentic_execution_contract.py`; add a pre-v8 SQLite fixture.

Work:

- Add `verifier_inputs` and `verifier_evaluations` tables with `CREATE TABLE IF NOT EXISTS` migration.
- Add atomic verifier reservation/cap logic inside the existing decision transaction.
- Combine grant consumption, exact input persistence, and send-boundary observation.
- Combine response observation and provider-action completion for v8 verifier calls.
- Add idempotent evaluation recording, conflict refusal, snapshot projection, retry eligibility, and usage derivation.
- Count unknown sends against allowance; exclude denials and proven `not_dispatched` reservations.

Gate:

- Old database opens and gains additive tables without changing existing v7 data.
- Cap 1/2, cross-identity counting, concurrent grants, unknown consumption, not-dispatched release, event order, and replay tests pass.
- Full suite passes with execution construction still on v7.

### Chunk 3: Gateway, runtime, and receipt cutover

Files/modules:

- `cli/delivery_gateway.py`, `cli/maf_supervisor.py`, `runtime/maf_runner/delivery_lead.py`.
- `cli/execution_contracts.py`, `cli/delivery_projection.py`.
- Extend gateway, runner, receipt, projection, and compatibility tests.

Work:

- Build v8/v2 artifacts for new chartered jobs.
- Persist the exact augmented verifier input before send.
- Record returned response and complete the action before evaluation, including provider/model mismatch as `unusable` rather than `unknown`.
- Send Flow-normalized pass, retry-eligible non-pass, or terminal failure back to Magentic.
- Require Magentic to propose the retry; Flow only grants or denies it.
- Project evaluations and usage into v8 receipts and require a bound valid pass for completion.
- Update inspection and runtime protocol handling without changing v7 behavior.

Gate:

- Deterministic scenarios pass: pass; fail then pass; unusable then pass; cap-one failure; two non-passes; manager stop; third-call denial; transport unknown; exact replay; changed replay; receipt tampering; and v7 read regression.
- Full repository suite passes.

## Dependencies and stop conditions

- Chunk 2 consumes the canonical evaluator and helpers from chunk 1.
- Chunk 3 depends on chunks 1 and 2.
- Each chunk must be independently mergeable and keep the full suite green.
- Stop for solution amendment if stock Magentic cannot receive and act on the normalized retry-eligible result without changing the approved ownership boundary.
- Stop if provider response observation cannot be made truthful without changing non-verifier producer result semantics.

## Session model advice

- Coordinator recommendation: judgment, `gpt-5.6-sol`, high effort, because the plan spans durable protocol, persistence, and receipt semantics.
- Active parent: unknown; no verified same-session identity was available.
- Effective delegated assignments: business-analyst and product-manager used working roles; architect used judgment; test-engineer used working.
- Switch performed: no.

## Recommended lane

- `flow-implement`, because the work spans multiple contract, persistence, runtime, migration, and validation surfaces across three ordered chunks.

