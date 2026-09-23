# Validation Results

## Result

Implementation validation passed for protocol v8 structured verifier evaluation.

## Evidence

- Full repository suite: `1353` tests passed, `1` skipped.
- Focused verifier, ledger, gateway, projection, and supervisor suite: `62` tests passed.
- Pinned stock Magentic bridge: protocol v8 accepted a normalized non-pass result and selected the verifier again for an explicit retry.
- Mutation check: changing a valid pass to `valid_fail` caused `test_valid_pass_is_bound_and_sealed` to fail; the evaluator was restored byte for byte and the focused suite passed afterward.
- `git diff --check`: passed.

## Proven behavior

- New chartered executions use protocol v8 with Shaper Contract v2 and Delivery Charter v2; v1 contracts and v7 execution records remain readable.
- Flow persists the exact verifier input, consumes the grant, and claims the send atomically.
- A received response completes before deterministic Flow evaluation. Malformed or oversized content becomes `unusable`; transport uncertainty remains `unknown`.
- A retry is allowed only after the latest evaluation is `valid_fail` or `unusable`, within the sealed one-or-two-call allowance.
- Completed handback requires the latest verifier evaluation to be `valid_pass`.
- Receipts bind verifier inputs, raw outputs, diff evidence, test evidence, evaluations, and ledger-derived usage. Counter and binding tampering is rejected.
- Concurrent duplicate proposals share one durable grant and cannot over-reserve the verifier allowance.

## Review disposition

Independent quality and test reviews initially requested changes for retry eligibility, atomic send preparation, oversized known responses, provider-fact honesty, receipt recomputation, concurrency, and stock Magentic retry proof. Those findings were corrected in `ea31a67` and covered by the final passing suite.

## Approved limitation

No live Ollama run was performed. The approved plan treats prior provider functionality as established and requires deterministic evidence for this slice.
