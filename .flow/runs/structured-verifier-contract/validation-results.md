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

## Refinement addendum (2026-09-23)

This addendum covers the refinement that fixes the findings in `review.md`. The scope and the engineer's decisions are in `refinement-plan.md`.

### Evidence

- Full suite (`python3.12 -m unittest discover -s tests`): 1368 tests passed, 0 skipped. The system `python3` is 3.9 and cannot import the repo.
- `git diff --check`: clean.
- Mutation checks. Each one broke one behavior, the covering test failed, and the source was then restored byte for byte:
  1. Dropping the contract instruction from the verifier input failed the contract test and every v8 receipt test, because receipt validation requires the instruction.
  2. Skipping the receipt's recomputation comparison failed only the "forged pass over fail output" tamper subtest.
  3. Skipping re-evaluation on replay failed the replay test.
  4. Reverting `resolve_unknown` to the generic 4096-byte validator failed the unknown-resolution test.
  5. Removing the check that ties the final evaluation to the receipt evidence failed the "diff rebound consistently" and "test evidence changed" tamper subtests.

### Proven behavior added

- Every v8 verifier input ends with Flow's versioned output-contract instruction. The instruction sits inside the digested input, and receipt validation refuses an input without it.
- A completed verifier call with no evaluation is re-evaluated when replayed, from the stored response and input binding, without a resend.
- In structured mode, the Ollama adapter returns received empty content and a differently reported model as completed observations, so Flow judges them as `unusable` rather than `unknown`. It retains up to 64 KiB of output instead of cutting at 4096 bytes. The structured-result validator is shared by the ledger's observe path, operator resolution, and the receipt path.
- Receipt validation re-runs the evaluation and requires the result to be identical. It also recomputes each input digest and requires one evaluation per completed verifier. On completed receipts it requires the final evaluation to be bound to the receipt's edit and test evidence. Ten tamper subtests cover this.
- The evaluator rejects a boolean or float `schema_version` and a reason code that doesn't match its disposition.
- v8 preparation refuses a Delivery Charter that did not seal `max_verifier_calls`.
- An expired verifier grant is committed as denied. When send preparation is refused, an untouched grant is released as `not_dispatched`.

### Not covered by a direct test

- The gateway's "pass bound to stale evidence" branch (`cli/delivery_gateway.py:999-1004`) is unreachable in a v8 run today. v8 attempts run fresh only, `resume_delivery` accepts v5 only, and the ledger denies a second producer turn. So edit and test evidence are captured exactly once per attempt. The branch exists so that a future v8 resume path fails closed.
- The `rowid` tiebreak and the supervisor message text have no dedicated tests.
- No live Ollama run was made. Under AC10 it remains optional and needs the engineer's approval.

