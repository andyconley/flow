# Implementation Handoff

## Status

Implementation is complete and ready for Flow review.

## Delivered

- Protocol v8 structured verifier candidate and Flow evaluation contracts.
- Shaper Contract v2 and Delivery Charter v2 with `max_verifier_calls` set to one or two, default two.
- Additive SQLite verifier input and evaluation records.
- Atomic verifier input binding, grant consumption, and send claim.
- Explicit Magentic-owned retry after a Flow-normalized non-pass.
- V8 receipts and inspection with evidence bindings and derived usage.
- V1 and v7 compatibility plus additive legacy database migration.
- ADR 0015 documenting the ownership boundary.

## Commits

- `d135158 feat: define structured verifier contracts`
- `abf25aa feat: persist structured verifier evaluations`
- `d2b4ffa feat: enforce structured verifier handback`
- `ea31a67 fix: enforce verifier retry and receipt truth`

## Validation

See `validation-results.md`. The final full suite passed with 1,353 tests and one skip. No live provider call was required.

## Next lane

Run `flow-review` against the approved requirements and acceptance criteria. Do not publish or merge until that review is accepted.

## Refinement after review (2026-09-23)

`flow-review` requested refinement: see `review.md`. The engineer approved fixing every Critical, Important, and Suggestion finding in the same run. The run stays in `reviewing`, because Flow has no transition back to implementation. The plan is in `refinement-plan.md`, and the evidence is in the addendum to `validation-results.md`.

### What changed

- The verifier input carries Flow's versioned JSON output contract (the review's Critical finding).
- Replay re-evaluates a completed verifier that has no evaluation. The Ollama adapter reports received facts honestly in structured mode. Receipts recompute and cross-bind the evaluation.
- The evaluator requires an integer `schema_version` and pairs each reason with its disposition. v8 refuses a Charter that never sealed a verifier cap. Expired and refused grants no longer stay reserved. Evaluation ordering has a `rowid` tiebreak. The supervisor message is corrected.
- A second review round found three more issues, now fixed:
  - Tying every binding to the final evidence could reject a legitimate rerun. Now only the final evaluation of a completed receipt is checked, and the gateway fails closed on stale evidence.
  - `resolve_unknown` still used the 4096-byte validator.
  - A failed grant release could mask the original error.

### Open items

- A controlled live Ollama run is advisable before relying on the prompt in production. Strict parsing may still yield many `unusable` results. `num_predict` was raised from 256 to 1024 for structured verifier calls so a full verdict fits.
- The Codex and Claude adapters still send `action["task"]` rather than `provider_task`. Neither is an approved verifier provider today, but a v8 verifier on either would never see the evidence or the contract.
- If a roster approved a model literally named `unreported`, a response that reports no model would match it. This is negligible in practice.

### Next lane

Run `flow-review` again on the refinement, then `accept-review` if it passes.

