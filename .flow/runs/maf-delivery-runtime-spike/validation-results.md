# Validation results: MAF Delivery Lead spike

Date: 2026-09-19. Decision candidate: **continue the MAF spike; do not adopt MAF as Flow's runtime yet**.

## Runtime evidence

| Test | Result | Limit |
| --- | --- | --- |
| Flow envelope | `maf_delivery_probe.py` denied excess delegations, concurrency, replans, and an unallowed role before dispatch. | A Magentic-generated later delegation was not passed through the same Flow gate. Paid budget was capped operationally, not by a Flow policy engine. |
| Definition reuse | All three integrated workers received the actual `lead-developer`, `quality-reviewer`, or `test-engineer` file as instructions; digests are in `research/mixed-provider-result.json`. | Artifact contracts, relevant memory, and copies of the same role were not exercised. |
| Mixed providers | One `ConcurrentBuilder` run returned Codex SDK, Claude Code, and Ollama worker outputs in a single MAF workflow. Codex status was `completed` with three result items and 17,737 reported total tokens; Claude answer matched; Ollama answer matched. | Codex output text was not independently checked; the wrapper reported status and item count. All tasks were read-only. |
| Magentic planning | Local Ollama manager generated a 1,571-character plan and stopped at `MagenticPlanReviewRequest` before worker dispatch (`max_round_count=2`, `max_reset_count=0`). | No approval, replan, actual specialist delegation, or Shaper decision was exercised after the plan gate. |
| Restart | `restart_probe.py` started a pending request in one OS process, then a second process resumed its file checkpoint and received `denied_by_flow`. | This used a stub. No provider session was resumed and no Flow/MAF state reconciliation was tested. |
| Receipt | `observe_receipt.py` independently checked current specialist digests, fixture Git HEAD, and a clean worktree. `research/receipt.json` links these with imported provider/session metadata. | Provider results were imported from terminal output and are not independently attested. No changed paths or final worker commit existed. |

The first Codex SDK preflight worker turn completed but its JSON serializer failed after the turn. Its result is **not durable evidence**. A later integrated Codex call supplied the recorded completion. The earlier one still counts as a provider call and usage. This exceeded the plan's one-task-per-provider bound; see the deviation in `plan.md`.

Claude Code reported $1.544519 for the preflight and $1.720265 for the integrated run: **$3.264784 measured Claude cost**, below the approved $10 cap. Each call used `--max-budget-usd 3`. Codex ran under the installed ChatGPT account, not an API key; its usage is not expressed as an incremental dollar charge in this evidence. **The total spend cap was therefore not independently enforceable or verifiable for this run. Dispatching Codex violated requirement 8's stop rule.** Ollama was local. No paid Magentic manager call occurred. No further provider calls are authorized under this run until the cost boundary is repaired.

The fixture baseline commit is `f23b769cd00636f11cb06d1c7e52e8b2add9e795`. After moving checkpoint artifacts outside the fixture, independent `git status --porcelain` was empty. The observer's receipt confirms zero changed paths. This is a read-only integration proof, not a commit-bound worker handback.

## Delivery Lead machinery comparison

| Function Flow would otherwise build | MAF evidence | Flow-owned work that remains |
| --- | --- | --- |
| Fan-out/fan-in and participant ordering | ConcurrentBuilder ran three real provider wrappers. | Dispatch authorization, unique instance IDs, provider wrappers, failure policy. |
| Execution planning | Magentic generated a plan and review request. | Validate plans against charter and budget; Shaper decision and escalation. |
| Specialist delegation and handoff | Builders and request interfaces exist in installed package. | Dynamic dispatch gate, artifact routing, authority enforcement; live handoff untested. |
| Checkpoint and process resume | File checkpoint restored a stub request across processes. | Durable Flow/MAF linkage, provider-session recovery, replay protection. |
| Tracing | MAF exposes workflow events; the probe captured bounded results. | Canonical Flow event/provenance schema and independent observer. |
| Receipt and system of record | No proof that MAF supplies independent Git or policy evidence. | Flow receipt, reconciliation, archive, memory, MCP surface. |

MAF appears to remove substantial coordination scaffolding, but the estimate cannot honestly be called 70% yet. No reviewed native-engine work breakdown or weighted implementation estimate exists, and the expensive boundary work remains Flow-owned. The observed probes justify another narrow live test, not adopting MAF as a committed dependency.

## Acceptance disposition

1. Envelope: **failed as a complete criterion** — initial denials and plan gate proved; dynamic delegation/paid budget authority not proved, and the Codex cost stop rule was violated.
2. Definitions/artifacts: **partial** — definition files proved; memory and artifact contracts not.
3. Codex/Claude/local mix: **passed for a read-only MAF concurrent workflow**.
4. Recovery: **partial** — separate-process stub checkpoint passed; live worker recovery not.
5. Evidence/receipt: **partial** — independent Git/digest observation passed; provider action/commit receipt not.
6. Roughly 70% reduction: **unproven**.

No production Flow dependency or runner changed. The freeze on a Flow-native DAG/scheduler/checkpoint/broad provider abstraction remains in force. Next test: one Magentic-originated delegation routed through Flow's policy gate, a checkpoint after live worker dispatch with restart/reconciliation, and a commit-bound receipt. Stop if any of these require MAF to own Flow authority.

Mutation check: not run; this is a research prototype outside the production runtime. Validation is against the prototype and installed packages, not a shipped Flow adapter.
