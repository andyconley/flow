# Validation plan: Minimal capability spike

## Required checks

1. **Reproduction:** Run the report's commands in a fresh disposable Python environment. Confirm recorded versions and import/interface results, or reproduce a clearly reported package/preflight block.
2. **MAF states:** Run the deterministic stub once. Verify `started -> pending_request -> checkpointed -> resumed -> terminal` or a documented public-API block. Verify an out-of-envelope decision is denied by Flow-side policy without MAF granting authority.
3. **Scope:** Confirm there was no Codex worker turn/model call, worktree, production package change, or Flow lifecycle transition during the spike. Review `git status` and changed paths against the plan.
4. **Evidence:** Match each report claim to a versioned API inspection, command result, or stub observation. Label subscription execution, effective sandbox/approval grants, real worker events, interruption, and receipt trust as unverified.
5. **Decision:** Check that the recommendation follows the concrete effort comparison and identifies the smallest live follow-up. A dependency block is an acceptable spike outcome if the decision states its limit.
6. **Hygiene:** `git diff --check`; inspect report/output for secrets and unbounded environment/log capture; `flow run validate-orchestration execution-provider-receipt-charter --stage dispatch` immediately before any Flow-managed delegation.

## Acceptance

- A reviewer can reproduce the bounded observations without chat history.
- The recommendation is limited to the next live test and does not claim a production runner is validated.
- All unknowns created by skipping a real worker are explicit.

No repo-wide suite, deployment, runtime install, or end-to-end worker test is required for this investigative spike. Those belong to the later worker slice.
