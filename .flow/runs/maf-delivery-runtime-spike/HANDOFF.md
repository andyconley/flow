# Handback: MAF Delivery Lead spike

**Decision:** MAF remains the preferred runtime candidate; do not adopt it as a Flow dependency yet. The integrated mixed-provider invocation and Magentic plan-review seam work, but the approved cost stop rule was breached for Codex and dynamic delegation was not Flow-gated. Independent review requests changes before acceptance.

What ran: one MAF concurrent workflow with read-only Codex SDK, Claude Code, and Ollama specialists using three existing Flow definition files; a local Magentic manager stopped at plan review; a separate-process stub checkpoint resumed with a Flow denial. See [validation results](validation-results.md), [review](review.md), and [reconciliation](reconciliation.md).

Paid accounting: Claude reported $3.264784 across two capped calls. Codex used ChatGPT sign-in and reported usage but no enforceable dollar cap; the $10 total could not be proven. The historical mixed-provider script entry point is disabled. Do not dispatch more paid workers under this run.

Next bounded work: design a demonstrably enforceable Codex cost boundary or leave Codex criterion unproven; route every Magentic-originated delegation through one Flow-owned cumulative gate; then test live workflow restart and a commit-bound independent receipt. Produce a weighted native-versus-MAF work breakdown for the 70% target. Preserve the freeze on Flow-native DAG, scheduler, checkpoint, and broad provider abstraction work until that decision.

No Flow production code, installed dependency, or provider configuration changed. Research artifacts are under this run; the disposable virtual environment and fixture are under `/private/tmp`.
