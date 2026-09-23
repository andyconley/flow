# Architecture Review

- Flow owns verdict parsing, evaluation, evidence binding, terminal status, and verifier allowance. Magentic selects an approved verifier; the provider returns candidate output.
- Do not silently change protocol-v7 completion semantics. The solution must choose an explicit new protocol or negotiated verifier-contract version while keeping v7 readable.
- Observe and complete the provider response before parsing the verdict so invalid structured output becomes a deterministic failed verification rather than an unknown call.
- Bind the Flow evaluation to action ID, verifier-input digest, raw-output digest, diff digest, and test-output digest.
- Enforce `max_verifier_calls` atomically in the ledger, independently from the global delegation cap.
- Route to `flow-solution` before planning because versioning and evaluation placement are durable contract decisions.

