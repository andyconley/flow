# Refinement Plan: Review Findings

This plan covers the findings in `review.md` that were approved for this pass. The run stays in `reviewing`, as the engineer decided on 2026-09-23. It returns to `flow-review` once this work is done.

## Engineer decisions (Phase 1)

- **Scope:** Critical 1, Important 3–5, and every suggestion. Important 2 is already fixed in `8a18415`.
- **Lifecycle:** keep the same run with no framework transition, and record this work as a refinement addendum.
- **Contract placement:** Flow appends a fixed, versioned instruction to the verifier's `provider_task`, inside the persisted and digested verifier input.
- **Output size:** v8 verifier calls pass output through up to the evaluator's limit. The evaluator, not the adapter, decides "oversized".

## Changes

1. **Critical 1: contract instruction.** Add `VERIFIER_CONTRACT_INSTRUCTION` to `cli/verifier_contracts.py`. It is tied to `VERIFIER_VERDICT_SCHEMA_VERSION`. The gateway appends it to `provider_task`.
2. **Important 3: re-evaluate on resume.** When a completed v8 verifier action is replayed and has no evaluation yet, the gateway evaluates the stored response against the stored input binding, records the result idempotently, and returns the same evaluation summary.
3. **Important 4: honest Ollama facts.** Add structured-verifier mode to `call_local`. In that mode:
   - empty content becomes an empty completed output;
   - a mismatched model is reported as returned, so Flow's check produces `provider_binding_mismatch`;
   - output is kept up to the ledger's 64 KiB response limit instead of being cut at 4096 bytes.

   A shared structured-result validator replaces the 4096-byte `validate_result` for v8 verifier results in the ledger, gateway, and receipt paths. `num_predict` rises from 256 to 1024 for these calls so a full verdict fits in the model's output.
4. **Important 5: receipt recomputation.**
   - Re-run `evaluate_candidate` over the bound output and digests, and require an identical evaluation.
   - Require the evaluation's diff and test digests to match `evidence.edit` and `evidence.tests`.
   - Require exactly one evaluation per completed verifier action.
5. **Suggestions:**
   - `schema_version` must be the integer 1, not `true` or `1.0`.
   - Each reason code must match its disposition.
   - v8 preparation refuses a Delivery Charter that did not seal `max_verifier_calls`, instead of defaulting it.
   - A verifier grant that expires inside `prepare_verifier_send` is committed as denied before the error is raised.
   - Evaluation ordering in the snapshot and usage queries gets the `rowid` tiebreak.
   - The supervisor error message is corrected.
   - Tamper tests change each bound field separately.

## Validation

- Focused suites first, then the full suite under `python3.12`.
- A mutation check: remove the contract instruction and confirm the covering test fails.
- No live Ollama run. It stays optional under AC10 and needs the engineer's approval.
