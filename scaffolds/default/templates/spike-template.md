# Spike Template

Two forms. Pick the form to match the work — see `solutioning-decisions.md` for the decision criteria the spike must answer.

## When to use which form

Use **Form A — Smallest viable** when all of these hold:

- Single owning team / single surface.
- Low architectural uncertainty (the question is "which of these two options," not "what shape should this take").
- 1 day of effort or less.
- No new contracts (API, event, edge spec) introduced.
- No cross-team dependencies surfacing.

Otherwise use **Form B — Full template**.

If you start in Form A and discover the work warrants escalation, switch to Form B — that switch is itself a finding worth recording.

## Form A — Smallest viable spike (1-page)

```md
# SPIKE: <concise problem/area>

- **Related:** [ticket/epic link]
- **Solutioning Lead:** [name]
- **Timebox:** [e.g., 4 hours; ends YYYY-MM-DD]

## Problem
[1–3 sentences. What decision must be made so delivery can proceed?]

## Options
### Option A: [name]
- Shape: [1–2 lines]
- Pros: [bullets]
- Cons: [bullets]

### Option B: [name]
[same structure]

## Recommendation
[Chosen option + rationale, or "engineer's call — here's how I'd decide."]

## Acceptance (this spike is done when)
- [ ] [Decision recorded]
- [ ] [Follow-up cards filed, if any]
- [ ] [Successor spike linked, if any]

## Owners and follow-ups
- [Decision: owner / by when]
- [Risks identified: each with named owner]
```

If the spike needs more sections, it isn't a smallest-viable spike anymore — move to Form B.

## Form B — Full spike template

```md
# SPIKE: <concise problem/area>

- **Related requirement/epic:** [link(s)]
- **Conducted by:** [names; note AI assistant use]
- **Solutioning Lead:** [name]
- **Timebox:** [e.g., "Up to 2 days, ends YYYY-MM-DD"]

## Goal and key questions

**Goal.** [One paragraph — what decisions must be made so delivery can be estimated and scheduled.]

**Key questions.**
1. ...
2. ...

## Out of scope

[Name what the spike isn't deciding — separate from per-task scope in the work breakdown.]

## Expected outcome and deliverables

Name the artifacts this spike will produce, with locations and owners. Don't say "we'll write a design doc"; say where it lives.

- **Design doc** — target location.
- **Implementation cards** — parent epic for follow-up cards.
- **ADRs** — any decision records this will produce.
- **Reviewers** — named people per relevant team.
- **Prototype** — branch / repo, if applicable.

If "not pursuing" is a possible outcome, say so up front (see `solutioning-decisions.md` — Done vs Rejected).

## Context and constraints

[1–3 paragraphs on current behavior and relevant architecture; link diagrams.]

**Constraints.** [Pull the relevant guardrails from `architecture.md`, `patterns.md`, applicable project overlays.]

## Dependencies

- **Blocks:** [work items that can't proceed until this spike resolves]
- **Blocked by:** [what has to land or be decided before this spike can close]

(Set ticket-link metadata too; the inline block keeps the relationships readable.)

## Approach

[How you'll explore — research, experiments, comparisons. Not the final design yet.]

## Findings and evidence

[Findings organized by key question, with answers. Evidence: links to diagrams, example payloads, prototype results, screenshots.]

## Proposed solution

**High-level design.** [1–2 paragraphs + a simple sequence/flow diagram (main path + one failure path).]

**Impacted components.**

| Layer/area | Components | Nature of change |
|---|---|---|
| ... | ... | ... |

**Contracts.** [API request/response, event schema/semantics, edge spec change + version bump if applicable.]

## Solutioning Lead considerations

The Lead checks the proposed solution against:

- **Architectural alignment** — fits within current system architecture; reuses existing components.
- **Modularity** — solution decomposes into manageable, independently shippable components.
- **Scalability** — accounts for growth in the relevant scale dimensions.
- **Testability** — automated tests can be written at the appropriate layer.
- **Iterative delivery** — incremental progress with usable behavior at each step.
- **Maintainability** — clean coding practices; future debugging and updates plausible.
- **Technical debt** — debt added, paid down, or deferred is explicit, not silent.

For deeper architectural review on non-trivial changes, walk the architect agent's five dimensions and consider whether the change warrants an ADR (see `architecture.md`).

## Criteria

- **Success criteria** — [business outcome the solution contributes to]
- **Acceptance criteria** — [per-task conditions for stakeholder acceptance; format as a checkbox list]
- **Definition of Done** — [which tier applies and what gates it carries; see `solutioning-criteria.md`]

## Work breakdown

| Task | Summary | Scope/constraints |
|---|---|---|
| T1 | ... | ... |

Each task must satisfy **INVEST** (Independent, Negotiable, Valuable, Estimable, Small, Testable, Measurable). If a task fails INVEST, break it down further.

## Implementation handoff (per task)

Each task carries the implementation-handoff fields — see `templates/implementation-handoff.md` for the full list (Problem, Desired Outcome, In/Out scope, User Journey/States, Design expectations, Technical constraints, Acceptance, Validation, Required handback).

## Test strategy

[What must be tested where — unit, integration/contract, E2E, evals.]

## Estimates and commitments

Estimates are forecasts, not promises. Spike-stage ranges narrow as understanding grows. The team commits to incremental value, quality (DoD), and transparency — not to specific dates pulled from spike estimates.

If a stakeholder needs a date: "current forecast is X; here's what would change it." Refine as work proceeds.

## Decisions, alternatives, open questions

- **Decisions made** (with rationale) — your architectural memory.
- **Alternatives considered and rejected** (with brief why).
- **Open questions** tracked separately, often as future spikes.

## Closure summary

When the spike resolves, post a structured closing comment:

```md
## Spike Closure Summary

### Produced by this spike
- [Design doc link]
- [ADR link, if any]
- [Prototype branch / repo, if any]

### Requirements coverage

| Requirement | Status | Notes |
|---|---|---|
| (req id) | Resolved / Deferred / Out of scope | ... |

### Remaining work

| Item | Estimate | Parent epic / ticket |
|---|---|---|
| ... | ... | ... |

### Open design questions
- [Question that did not get decided; what would unblock it]

### Successor spike
- [Link if applicable; "none required" otherwise]
```

A one-liner ("design doc linked, cards groomed") is fine for trivial spikes. Use the structured form whenever the spike produced architectural decisions or follow-up cards.

## Investigation spike variant

For bug-shaped investigations, use this lighter shape instead of the full template:

```md
### Expected
[What the system should do]

### Actual
[What the system actually does]

### Steps to reproduce
1. ...

### Background
[Relevant context, prior tickets, related telemetry]

### Acceptance criteria
- [ ] Investigate to root cause.
- [ ] If a fix is warranted, create a linked Bug card with reproduction steps.
- [ ] If not a defect, document the explanation in the closure comment.
```

Use this when the spike's job is "figure out what's going on with X" rather than "decide how to build X." Keep the same Header, Out of scope, Expected outcome, and Closure summary discipline.
