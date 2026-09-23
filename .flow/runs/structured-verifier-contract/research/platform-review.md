# Platform Review

- Use protocol v8 and keep v7 validation and reading unchanged.
- Persist exact verifier input before send and Flow evaluation after the provider response is durably observed.
- Use additive `verifier_inputs` and `verifier_evaluations` records rather than overloading provider results.
- Enforce the total verifier-call cap atomically in the ledger; unknown sends consume allowance and proven not-dispatched reservations do not.
- Let Magentic propose the retry after receiving Flow's normalized evaluation. Flow authorizes or denies it and never silently dispatches a retry itself.
- Replace scattered hard-coded protocol sets with named compatibility helpers during implementation.

