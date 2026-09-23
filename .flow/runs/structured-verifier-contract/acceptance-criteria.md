# Acceptance Criteria

1. A valid structured pass tied to the exact verifier input, raw output, diff, and targeted-test evidence permits the existing completion gate to succeed.
2. A valid structured fail makes the attempt failed, preserves bounded findings, and never produces a successful handback.
3. Missing or malformed JSON, extra or missing fields, unsupported versions or decisions, oversized values, pass with blocking findings, fail without findings, wrong evidence binding, provider mismatch, and conflicting replay payloads fail deterministically before handback.
4. Flow records a completed provider response before evaluating its verdict. Invalid verdict content yields a completed provider action plus failed verifier evaluation; transport uncertainty alone yields `unknown`.
5. With the default `max_verifier_calls: 2`, Flow permits one initial verifier call and at most one retry after a valid fail or unusable verdict. A third proposal is denied before adapter invocation even when global delegation and paid-call budgets remain. A charter may narrow the cap to one, which disables retry.
6. The receipt reports the allowed and consumed verifier calls separately and contains the structured evaluation and its evidence digests.
7. A verifier proposed before the observed edit and passing targeted test remains denied before send. Producer and verifier identities remain distinct and the verifier remains read-only.
8. Existing v7 receipts remain readable and retain their original semantics. New executions use the versioning mechanism approved in `flow-solution`.
9. Focused tests cover valid pass, valid fail, every unusable-output class above, cap enforcement, truthful response observation, replay, and legacy compatibility.
10. No new Ollama availability smoke is required. A controlled live job is optional only if implementation needs to validate that the prompt reliably elicits the contract.
