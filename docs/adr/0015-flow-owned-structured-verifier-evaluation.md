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

## Amendment: verifier prompt and constrained decoding (2026-09-25)

A live check found that local models could not satisfy the contract. The
verifier's system message was its full role body, and that body ends in the
role's own markdown `## Output Format`. The models followed that format and
ignored the JSON contract appended to the task.

- **Derived system instructions.** At send time, a v8 verifier gets
  `verifier_instructions(role_body)`. That is:
  - a preamble saying Flow's contract overrides any other output format;
  - the sealed role body with its `## Output Format` section removed,
    including any fenced template inside it;
  - `VERIFIER_CONTRACT_INSTRUCTION`.

  The roster keeps the sealed role body and its `definition_digest`, so the
  Delivery Charter seal is unchanged. The derivation is deterministic code,
  just as the contract suffix on the digested task is.
- **Constrained decoding.** Ollama verifier calls send `VERIFIER_OUTPUT_SCHEMA`
  as `format`. The schema only guides decoding. It cannot express byte limits
  or the pass/fail finding rules, so `evaluate_candidate` stays the only judge
  and the parser stays strict: no stripping of fences or prose.
- **Thinking.** Thinking models keep their default. An empty reply is judged
  unusable and uses the verifier allowance, which fails closed.
