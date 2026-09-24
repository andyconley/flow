# Implementation handoff

## Outcome

The bounded capability spike is complete. Keep Flow as the first execution coordinator and defer Microsoft Agent Framework (MAF) adoption. This is a decision about the next live test, not a production runner decision.

## Evidence

- `openai-codex` 0.154.0 and `agent-framework-core` 1.19.0 were installed in a disposable Python 3.12.13 environment.
- SDK inventory observed public controls for working directory, sandbox and approval mode, thread start/resume, turn events/results, and interruption. No SDK client or model turn was created.
- The MAF stub exercised a pending request, Flow-side simulated denial, two checkpoints, restoration in a new workflow instance, and terminal output. No model call occurred.
- Repeated runs matched the captured bounded JSON, including a fresh pinned environment. A mutation check failed closed as expected when the policy action changed.
- MAF carried the request and checkpoint state but did not replace Flow policy, receipt observation, or reconciliation; it would add another state store.

See [reuse-spike.md](research/reuse-spike.md), [validation-results.md](validation-results.md), [spike-review.md](research/spike-review.md), and [reconciliation.md](reconciliation.md) for commands and evidence boundaries.

## Not proven

Subscription-backed SDK execution, effective sandbox or approval grants, real session events, interruption, isolated worktree changes, commit handback, trusted receipt integrity, process-restart recovery, and production delegated-approval enforcement remain unverified. The MAF negative integration result is limited to the inspected core package and version.

## Next action

Run the smallest live proof: one disposable-repository Codex SDK worker under the existing ChatGPT sign-in, in one isolated worktree, making a constrained change. Flow should independently observe the baseline, changed paths, validation, resulting commit, and handback receipt. Reconsider MAF only if that probe exposes a recovery or coordination gap its checkpoint/request mechanisms can close.
