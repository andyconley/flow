# Validation Plan

## Chunk 1

- Table-driven pure evaluator tests for valid pass/fail and every malformed, oversized, contradictory, provider-mismatch, and binding-mismatch reason.
- Cap validation for omitted/default 2, explicit 1/2, and invalid values including bool/string.
- Frozen v7 envelope and receipt remain readable with no inferred v8 fields.
- Full suite.

## Chunk 2

- Open a pre-v8 SQLite fixture; verify additive tables and unchanged legacy rows/snapshot.
- Assert durable order: input binding, send claim, response observation, provider completion, evaluation.
- Prove invalid content remains completed plus unusable; transport loss remains unknown without evaluation.
- Prove exact replay, conflicting replay refusal, cap 1/2, shared counting across verifier identities, unknown consumption, not-dispatched release, and concurrent atomicity.
- Full suite.

## Chunk 3

- Valid pass completes and receipt carries exact evaluation bindings and derived usage.
- First fail/unusable followed by an explicit Magentic retry and pass completes with exactly two sends.
- Cap one blocks retry; two non-passes end failed; a third proposal is denied before adapter invocation.
- Manager stop after a retry-eligible non-pass ends without an invented send.
- Transport uncertainty remains unknown.
- Mutating action, input, raw output, diff, or test evidence makes receipt validation fail.
- Exact proposal replay does not resend; changed replay refuses.
- Existing pre-evidence denial, producer/verifier separation, read-only enforcement, v6 inspection, and v7 readability tests remain green.
- Final full repository suite.

## Runtime evidence

- No live Ollama run is required. The predecessor run already established provider functionality; this slice proves deterministic contract and policy behavior.

