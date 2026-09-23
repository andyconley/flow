# Reconciliation

- The business analyst and product manager considered the fixed contract suitable for direct planning.
- The solution architect identified a durable unresolved choice: changing v7 in place versus introducing an explicit new or negotiated verifier-contract version.
- Disposition: route to `flow-solution`. Preserve v7 semantics and decide the compatible versioning and evaluation-record placement before planning.
- All reviewers agreed on Flow ownership, fail-closed handling, truthful observed-call status, a separate one-call verifier cap, and the listed non-goals.

## Solution disposition

- Engineer selected protocol v8.
- Engineer selected a configurable verifier-call cap with default two total calls: initial plus one retry.
- A non-pass evaluation is terminal for its action. The attempt may continue once while allowance remains; otherwise it is terminal failed.
- Selected separate Flow-owned verifier input and evaluation records over embedding Flow judgment in provider result data.
