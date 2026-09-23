# Solution test review

## Existing seams to reuse

- Chartered gateway tests already cover Flow-granted producer/verifier dispatch, ordering, duplicate grants, provider substitution denial, source drift, delegation caps, and zero-send refusal.
- Recovery tests cover owner generation fencing, unknown-call handling, checkpoint binding, append-only continuation, and cross-process single-send behavior.
- Magentic tests exercise the pinned supervised manager and action proposals.

## New deterministic proofs

1. Stable canonical Shaper/Delivery digests and required-field rejection.
2. Idempotent `start-plan` sealing and no duplicate handoff/claim.
3. Zero-send denial before transition or outside charter.
4. One active owner generation; stale predecessor fenced before ledger mutation or send.
5. Cross-runtime reopen by run/charter identity without transcript dependence.
6. Valid and malformed v6 records remain inspectable but execute/resume-ineligible.
7. Projection conformance from Delivery Charter to the new envelope.
8. Deterministic Magentic producer-to-Ollama-verifier receipt flow.

## Live acceptance

Use one small Flow repository change with stock Magentic selecting an approved Claude or Codex producer and a distinct Ollama verifier. Require grants for manager and specialist calls and a receipt linking charter, handoff, owner generation, diff, test, and verifier evidence. Keep this live job outside routine deterministic CI.

## Requirement reconciliation

The earlier feasibility-probe criterion is superseded by the engineer's explicit decision that ChatGPT Work local access is established. Replace the probe with direct adapter contract tests when cross-runtime continuation is implemented.
