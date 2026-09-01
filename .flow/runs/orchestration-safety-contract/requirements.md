# Orchestration Safety Contract Requirements

## Problem

Flow routes role agents and records lifecycle artifacts, but its handoffs do not currently enforce whether briefs fit declared capabilities, concurrent writers have disjoint ownership, shared external mutations have recoverable baselines, agent claims retain their evidentiary status, disagreements are dispositioned, or high-risk acceptance is independently verified.

## Intended outcome

Flow provides one runtime-neutral orchestration contract used across existing lanes. A machine-readable run artifact and phase-aware CLI validator prevent structurally unsafe delegation and acceptance while preserving Flow's small lifecycle state and low ceremony for routine work.

## Behavioral requirements

1. Publish one canonical orchestration standard and reusable templates for agent briefs, orchestration manifests, findings reconciliation, and external mutation records.
2. Require briefs to declare objective, evidence inputs, allowed read/write scopes, required and confirmed capabilities, ownership, output path and format, success criteria, and claim-status expectations.
3. Validate orchestration manifests before dispatch and again at handback and acceptance gates.
4. Reject missing required fields, output paths outside declared write scopes, undeclared or overlapping concurrent writes, invalid risk classifications, unresolved reconciliation, and missing high-risk verification evidence.
5. Distinguish capability status as confirmed, missing, or unknown. Never present unknown runtime grants as confirmed access.
6. Preserve material claim status as observed, inferred, recommended, or unverified until the orchestrator explicitly dispositions it against evidence.
7. Record material agreements, conflicts, accepted or rejected conclusions, deferrals, decision owner, and evidence used to reconcile multi-agent work.
8. For shared or external mutation, record exact target identity, a fresh baseline, expected change, writer ownership or serialization, recovery posture, exact execution results, post-write readback, comparison, and unexpected-delta disposition. Git is the repository baseline.
9. Require independent verification for any hard risk trigger or at least two aggravating factors. Record producer, evidence collector, reviewer, and independence for all work.
10. Preserve active revision-1 and `legacy/inferred` runs. Apply new enforcement to protocol-revision-2 runs without retroactive breakage.
11. Integrate the contract with existing Flow lanes rather than adding an orchestrator command or lifecycle phase.
12. Complete canonical source changes, tests, documentation, adapter regeneration, review, commit, push, automated release, release verification, and install/update verification.

## Risk classification

Any hard trigger makes work high risk:

- destructive or irreversible action, including unproven recovery
- production or shared external-system mutation
- authentication, authorization, secrets, privacy, or security-boundary change
- schema or data migration with plausible loss, corruption, or rollback failure
- financial, legal, personnel, safety, or customer-access consequences

Without a hard trigger, two or more aggravating factors make work high risk:

- large blast radius
- weak rollback
- poor or delayed observability
- concurrency or cross-system coordination
- material unresolved ambiguity
- author-only validation
- an unverified agent claim proposed for a durable source of truth

## Constraints

- Use only Python's standard library for CLI validation.
- Keep lifecycle projection in `run.json`; keep detailed orchestration state in a referenced artifact.
- Validate declared structure and evidence existence, not semantic truth or inaccessible runtime state.
- Do not automate arbitrary SaaS snapshots, credentials, connectors, recurring scheduling, or fabrication detection in this release.
