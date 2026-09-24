# Implementation handoff: Minimal capability spike

- Work item: `execution-provider-receipt-charter`
- Work type: investigative spike; no production runner
- Owner: lead developer
- Inputs: [approved requirements](requirements.md), [accepted solution](solution.md), [plan](plan.md), [validation plan](validation-plan.md)

## Desired result

Produce `research/reuse-spike.md` with an evidence-backed recommendation for the least-effort next live worker proof. The report must distinguish inspected SDK capability from exercised behavior and from unknown subscription/runtime behavior.

## Implementation instructions

1. Use an isolated Python environment in a temporary or run-local nonproduction location. Install only the Codex SDK and MAF packages required for the inspection/stub; record exact package versions and source links. Do not add them to Flow's package metadata.
2. Inspect public Codex SDK imports/signatures/docs for work directory, sandbox, approval mode, thread/session identity, event/result handling, interrupt, and resume. Do not start a Codex turn or send a prompt. A read-only `codex login status` may establish the CLI's current authentication mode, but does not prove SDK subscription execution. Redact account identifiers and credential material.
3. Write the smallest deterministic MAF stub under `research/spike/`. Demonstrate start, pending request, bounded response, checkpoint, resume, and terminal result. The stub must make no model call and must not use a Codex harness. Simulate one Flow policy rejection outside a delegation envelope independently of MAF.
4. Keep all prototype code and evidence out of production `cli/` and `scaffolds/`. Compare the prototype with the Flow-only approach using concrete modules, dependencies, persistent state, and reconciliation paths. Do not count lines of code as the sole effort measure.
5. Conclude `keep_flow`, `adapt_maf_for_live_probe`, or `defer_maf` as a next-test recommendation. State which real-worker checks remain open and the exact smallest follow-up experiment.

## Limits and failure handling

- No real worker, model call, worktree, lifecycle transition, receipt, external mutation, or production dependency adoption.
- If package install/import is blocked, capture the error and installed environment facts, then stop that branch. Do not work around it by using private APIs or broadening the spike.
- If the MAF public API cannot support a minimal checkpoint/pending-request path, record that and stop; a failed probe is a useful result.
- Do not store secrets, raw auth files, full environment dumps, or worker transcripts.

## Required handback

- Paths to report, prototype, and bounded evidence; exact package versions and commands.
- Observed result for each capability and stub state; failure/blocked evidence where applicable.
- Qualitative effort comparison, recommendation, unresolved risks, and required live follow-up.
- Validation results and any deviation from the agreed narrow scope.
