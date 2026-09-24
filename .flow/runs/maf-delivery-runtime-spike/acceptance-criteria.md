# Acceptance criteria: MAF Delivery Lead decision spike

- A reproduced run demonstrates Flow denial for each envelope dimension and for a runtime-originated expansion, with the denial recorded in Flow.
- The run uses Flow's actual specialist definitions, shared charter, constraints, and artifact contracts; copied roles have distinct instance IDs.
- Codex, Claude, and local workers each execute a bounded task in one MAF-managed workflow, or the criterion is reported failed with a specific blocker.
- A separate process resumes from a checkpoint and the Flow run reconciles without duplicate dispatch or lost evidence.
- A Flow-side receipt links charter and definition digests, provider/session identity, allowed actions, changed paths, validation, and commit; the result can be checked without trusting only MAF's self-report.
- A reviewed work breakdown gives a defensible estimate of Delivery Lead code/state avoided by MAF and added by adapters/reconciliation; the roughly 70% target is assessed explicitly.
- Final decision is adopt, reject, or continue spike, with failed criteria and a bounded next action. No production dependency is added solely on stub evidence.
