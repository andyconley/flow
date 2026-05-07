# flow-implement

Use `flow-implement` for gated implementation work when the task is large enough to benefit from explicit phases and durable artifacts.

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

Primary roles:

- `lead-developer` for execution plan and slice sequencing
- `architect` when boundaries, integrations, or ADRs are involved
- `ux-specialist` when user-facing behavior changes
- `data-engineer` when persistent state changes
- `test-engineer` for prove-it coverage and verification strategy
- `code-reviewer` for merge-readiness review
- `security-reviewer` and `sre` when the change touches riskier surfaces
- `tech-writer` for final durable handback

This command is the orchestrated lane for multi-phase execution. It should make role handoffs explicit.

## Phases

1. requirements
2. as-is
3. plan
4. implementation
5. review
6. validation
7. handback

## Phase Expectations

### 1. Requirements

- confirm the work is implementation-ready
- identify missing assumptions or contradictions
- escalate back to `flow-plan` if needed

### 2. As-Is

- inspect current code, behavior, and constraints
- identify where the change actually lives

### 3. Plan

- create file-level change plan
- define test and rollout strategy
- create run artifacts

### 4. Implementation

- make the code changes
- keep the slice incremental and reviewable

### 5. Review

- run structured review with the right roles
- capture findings and dispositions

### 6. Validation

- collect automated, manual, and runtime evidence

### 7. Handback

- summarize what changed
- summarize proof
- record remaining risks and next actions

## Output Format

```md
## Implementation Run Summary

### Work ID
- [Run identifier]

### Phase Status
- Requirements:
- As-is:
- Plan:
- Implementation:
- Review:
- Validation:
- Handback:

### Roles Engaged
- [Role and why]

### Change Surface
- [Files/modules changed]

### Validation Evidence
- [Tests, manual checks, runtime checks]

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
