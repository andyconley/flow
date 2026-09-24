# Validation plan

- Focused policy tests verify unknown work remains counted, duplicate request IDs fail closed, and the cumulative caps still apply after completed replans.
- Run a denied Magentic specialist request and verify Flow denial plus zero dispatch rows.
- Verify a separate child process observes at least one Ollama stream update, records `unknown`, and exits intentionally before MAF finishes.
- Resume the same MAF checkpoint in another process. Check stable request identity, zero additional dispatch rows, and a terminal manual-reconciliation result.
- Recompute charter/definition digests and inspect fixture Git HEAD/status, policy events, and checkpoint from a Flow-side observer. Label provider output and physical call counts accurately.
- An independent reviewer checks the boundary and data claims. Mutation check changes a cap in a temporary policy fixture and confirms the covering test fails.
