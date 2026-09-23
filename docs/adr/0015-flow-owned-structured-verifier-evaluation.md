# ADR 0015: Flow-owned structured verifier evaluation and bounded retry

- Status: accepted
- Date: 2026-09-23

## Decision

Protocol v8 introduces a closed verifier candidate schema and a separate,
Flow-owned evaluation record. A provider supplies JSON containing a decision,
summary, and findings. Flow binds the parsed outcome to the completed verifier
action, exact verifier input, raw output, observed producer diff, and targeted
test evidence. Only Flow decides whether that candidate is a valid pass, a
valid fail, or unusable.

The Shaper Contract v2 and Delivery Charter v2 carry
`max_verifier_calls`. It is an independent allowance of one or two total
verifier calls, defaulting to two. Flow reserves this allowance atomically
before a provider send. Magentic may propose a retry after a non-pass; Flow
does not silently send one.

## Consequences

A received provider result is observed and completed before Flow evaluates its
content. Malformed or contradictory content is therefore a known completed
call with an unusable evaluation; transport uncertainty remains `unknown`.
One non-pass is retry-eligible only when the sealed allowance remains. A
second non-pass, or any non-pass at an allowance of one, ends the attempt.

V7 receipt validation and historical meaning remain unchanged. The v8
evaluator, contract versions, and named protocol capability helpers are added
before runtime cutover, so active construction continues to emit v7 until the
gateway and ledger support the new state transitions.

## Recovery

Provider observations, verifier inputs, and Flow evaluations are distinct
durable records. Exact evaluation replay is idempotent; changed evidence or
output bindings are rejected. The first irreversible boundary remains the
provider send, and unknown sends consume the verifier allowance unless Flow
can prove they were never dispatched.
