# flow-implement

Use `flow-implement` for gated implementation work when the task is large enough to benefit from explicit phases and durable artifacts.

<HARD-GATE>
Do NOT proceed past Phase 1 (Requirements) into current-state inspection, planning, or implementation until missing assumptions, contradictions, or ambiguities in the requirements have been surfaced to the engineer and either resolved or explicitly waived. "I confirmed the requirements myself" is not enough — Phase 1 produces a user-facing check-in. Implementation that starts on inferred requirements produces wrong code, however clean the phases that follow.
</HARD-GATE>

## Overview

This command is the main execution lane for substantial work. It coordinates planning, implementation, review, validation, and handback so multi-file or multi-session changes stay auditable and recoverable.

## When to Use

Prefer this command when:

- work spans multiple files or sessions
- architecture, data, UX, or rollout decisions matter
- the work needs durable artifacts for review and handback
- the slice is too large or risky for `flow-scout`

**When NOT to use:** tiny self-contained changes that fit comfortably in `flow-scout`, or requirement-shaping work that still belongs in `flow-plan`.

## Primary inputs

- implementation-ready requirements
- current architecture and standards
- relevant project overlays
- current codebase and tests

Artifacts should live under:

- `.flow/runs/<work-id>/`

## Primary outputs

- durable run artifacts
- implementation plan
- code and test changes
- review and validation evidence
- structured handback

## Composition

Core roles (always invoked):

- `lead-developer` for execution plan and slice sequencing
- `test-engineer` for prove-it coverage and verification strategy
- `quality-reviewer` for acceptance-readiness review
- `tech-writer` for final durable handback

Conditional roles (invoked when relevant):

- `architect` when boundaries, integrations, or ADRs are involved
- `ux-specialist` when user-facing behavior changes
- `data-engineer` when persistent state changes
- `security-reviewer` when the change touches sensitive or risky surfaces
- `sre` when rollout, runtime, or operational risk is non-trivial

This command is the orchestrated lane for multi-phase execution. It should make role handoffs explicit.

## Phases

1. requirements
2. current state
3. plan
4. implementation
5. review
6. validation
7. handback

## Phase Expectations

### 1. Requirements

- confirm the work is implementation-ready
- identify missing assumptions, contradictions, or ambiguities — and surface them to the engineer for resolution; do not proceed on inference. If everything is clear, say so explicitly ("requirements are fully specified, no clarifications needed") before moving to Phase 2 — that statement is the user-facing check-in
- escalate back to `flow-plan` if requirements turn out to be under-specified rather than just unclear
- **Hard checkpoint**: do not move to Phase 2 until either (a) every surfaced ambiguity has been resolved by the engineer, or (b) you have explicitly stated "no clarifications needed" and the engineer has not pushed back

### 2. Current state

- inspect existing artifacts — code, docs, configurations, prior runs
- identify where the change actually lives and what it touches
- **when inspection fans out into parallel investigation**, decompose into questions that are answerable independently — no dependencies between them, or the parallelism is not real — and give each investigator one question. Investigators write their analysis to `.flow/runs/<work-id>/research/<topic-slug>.md` and return only a short summary plus the path; the orchestrator reads the files rather than holding every finding in context
- **collect the returned paths and pass them all forward** when synthesizing. Synthesizing from the inline summaries alone discards the detail the files were written to hold, which is the failure mode this pattern exists to avoid
- reports live under the run because they are run artifacts: they archive with it, they are readable by `flow-archive`, and the work id already makes their location unambiguous

### 3. Plan

- create a concrete change plan at the right granularity for the work — file-level for code, section-level for documents, component-level for configurations
- define validation and rollout strategy
- create run artifacts under `.flow/runs/<work-id>/`

### 4. Implementation

- make the changes — code, docs, or other artifacts as the work requires
- keep the slice incremental and reviewable
- **commit per Conventional Commits** — every commit message follows `standards/git-commits.md` (type prefix required; breaking changes declared explicitly; one logical change per commit). When the slice itself is a breaking change, the commit message records it

### 5. Review

- run structured review with the right roles
- capture findings and dispositions
- **Every brief carries an evidence inventory** — what already exists in the area under review, with paths. Without it a reviewer cannot tell absent from unfound, and "X is missing" is an unsupported finding. See `standards/evidence.md`; `templates/adversarial-review.md` has the block.

### 6. Validation

- collect automated, manual, and runtime evidence
- state whether a mutation check ran — break one behavior, confirm the covering
  test fails, restore — and if not, why
- when a check ran anywhere but against the thing being changed, give a verdict
  per check rather than per environment. See `standards/evidence.md` for both.

### 7. Handback

- summarize what changed
- summarize proof
- record remaining risks and next actions

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

```md
## Implementation Run Summary

### Work ID
- [Run identifier]

### Phase Status
- Requirements:
- Current state:
- Plan:
- Implementation:
- Review:
- Validation:
- Handback:

### Roles Engaged
- [Role] - ran | absorbed by orchestrator | skipped - [why the role, and for absorbed/skipped, why that happened]

### Change Surface
- [Files/modules changed]

### Validation Evidence
- [Tests, manual checks, runtime checks]
- mutation check: ran (behavior broken, test that caught it) | not run (why)
- validated against: [the change itself, or surrogate + per-check transfer verdict]

### Handback
- [What shipped or is ready]
- [Risks / follow-ups]
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I'll just do the whole thing in one pass." | Large undifferentiated changes are harder to review, recover, and validate. |
| "We can skip the artifact trail since I know what I'm doing." | Durable artifacts are what let the work survive session loss and review. |
| "Review and validation can happen at the end if there's time." | Without planned review and proof, the slice is not complete. |
| "This doesn't need role handoffs." | Multi-surface work needs explicit perspective shifts to avoid blind spots. |

## Red Flags

- multiple phases implied but not recorded
- implementation phase started without an explicit Phase 1 check-in with the engineer
- ambiguities were "resolved by inference" rather than surfaced to the engineer
- implementation starts before requirements are stable
- no explicit validation evidence
- review is reduced to "looks fine"
- run artifacts do not explain current state

## Escalation Rules

- Escalate to `flow-plan` if requirements are incomplete.
- Escalate to `architect` if boundaries or migration risk are unclear.
- Escalate to `flow-review` if acceptance is still uncertain after implementation.

## Verification

Before leaving `flow-implement`, confirm:

- [ ] the run has durable artifacts under `.flow/runs/<work-id>/`
- [ ] the phase status is explicit
- [ ] code and tests changed in reviewable slices
- [ ] review findings are recorded and dispositioned
- [ ] validation evidence is explicit
- [ ] handback is complete enough for acceptance review or archive

## Finish Criteria

`flow-implement` is done when the work has durable artifacts, explicit review and validation evidence, and a handback suitable for archive or acceptance review.
