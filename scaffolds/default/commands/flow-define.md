# flow-define

Use `flow-define` for early feature or architectural-capability definition: ideation, scope discovery, evidence gathering, and requirements approval before `flow-plan` or `flow-solution`.

<HARD-GATE>
Do NOT produce approved requirements, route to `flow-plan` / `flow-solution`, or declare the definition complete until the definition has passed discovery, research/evidence review when needed, adversarial review, and explicit engineer approval. A definition that skips questioning creates polished requirements around untested assumptions.
</HARD-GATE>

## Overview

This command turns a vague idea, feature concept, or architectural capability into approved requirements. It is the phase before planning and solutioning.

Where `flow-solution` decides which technical approach fits approved requirements, and `flow-plan` turns approved scope into an implementation-ready plan, `flow-define` decides what outcome and requirements are worth pursuing.

The command runs in six phases:

1. intake
2. discovery
3. research and evidence
4. adversarial review
5. requirements capture
6. approval and routing

## When to Use

Use this command when:

- the user has an idea but not agreed requirements
- feature scope, target users, outcomes, or non-goals are still forming
- an architectural capability needs definition before solutioning
- research may be needed to understand precedent, standards, user pain, or operational evidence
- `/flow-boot` sees a vague new idea and needs a default next lane

**When NOT to use:** bug reports or defect investigations that already have expected/actual behavior; route those to `flow-plan` for now. Do not use this once requirements are already approved; route to `flow-solution` or `flow-plan`.

## Primary inputs

- idea, feature concept, capability request, or project-scope question
- available user, support, operational, market, or standards evidence
- project overlay context and active standards
- any known constraints, risks, or non-goals

## Primary outputs

- approved requirements, or a clear not-yet-approved disposition
- recommended durable artifact or structured chat summary
- role-owned research notes when evidence is needed
- adversarial review findings and dispositions
- next-lane recommendation: `flow-solution`, `flow-plan`, further definition, or defer/reject

## C-Lite Run Protocol

For durable definition work, create or update the run through the CLI rather
than editing lifecycle state by hand:

```bash
flow run transition <work-id> start-definition
flow run transition <work-id> approve-definition \
  --artifact requirements=.flow/runs/<work-id>/requirements.md \
  --artifact acceptance_criteria=.flow/runs/<work-id>/acceptance-criteria.md
```

Do not route to `flow-solution` or `flow-plan` until `approve-definition`
succeeds. A refused transition is a hard gate, not advisory prose.

## Orchestration safety

Revision-2 runs persist `orchestration_manifest=.flow/runs/<work-id>/orchestration.json`. Follow `standards/orchestration.md` and run `flow run validate-orchestration <work-id> --stage dispatch` immediately before delegation or shared mutation; `approve-definition` rechecks it.

## Composition

Core roles:

- `business-analyst` for users, workflows, ambiguity, current pain, and acceptance criteria
- `product-manager` for outcome, value, priority, success criteria, and non-goals
- `solution-architect` for capability boundaries, standards, precedent, feasibility signals, and decision surfaces

The opener depends on the request:

- `product-manager` opens when the problem is user, business, or priority led.
- `solution-architect` opens when the problem is platform, architectural, or capability led.

All three core roles participate in discovery, research proposal, adversarial review, and approval readiness.

Conditional roles:

- `sre` for operational incidents, alerts, reliability pain, rollout constraints, or observability gaps
- `support-lead` for support burden, recurring user confusion, troubleshooting gaps, and escalation evidence
- `test-engineer` for measurable acceptance, validation feasibility, and testability risks
- `security-reviewer` for abuse cases, sensitive data, auth, policy, compliance, or third-party risk
- `data-engineer` for data ownership, persistence, schema, migration, and lifecycle concerns
- `ux-specialist` for interaction models, user journeys, accessibility, and content clarity

## Definition Workflow

### Phase 1 - Intake

Classify the request:

- feature
- architectural capability
- workflow/process capability
- not definition-shaped; route elsewhere

Confirm:

- who the definition is for
- what outcome the user is trying to reach
- whether this is bug-shaped work that should stay in `flow-plan`
- whether the current conversation can use a structured chat summary or needs durable artifacts

### Phase 2 - Discovery

Clarify the problem before researching or writing requirements.

Cover:

- problem or opportunity
- target users, operators, or maintainers
- current workflow or current limitation
- desired outcome
- success criteria
- known constraints
- explicit non-goals
- assumptions and open questions

### Phase 3 - Research and Evidence

Research is optional, but the decision to skip it is explicit.

Any core or conditional role may identify a research need. Research must answer a named question, not gather background generally. Use `standards/research-evidence.md` to choose each role's research focus.

Examples:

- What standards govern this kind of work?
- What internal precedent should we mirror?
- What do comparable tools or teams do?
- What user reports, support tickets, or feedback prove this matters?
- What operational incidents, alerts, or support load make this urgent?
- What security, privacy, data, or rollout constraints should shape requirements?

For lightweight work, summarize the evidence inside the definition output. For substantial work, write one note per question under:

```text
.flow/runs/<work-id>/research/<topic-slug>.md
```

Use `templates/research-note.md`. Research is complete only when each finding has an implication for requirements.

### Phase 4 - Adversarial Review

Before requirements can be approved, the roles challenge the draft from their accountable perspectives.

**Every brief carries an evidence inventory** — what already exists in the area under review, with paths. Without it a reviewer cannot tell absent from unfound, and "X is missing" is an unsupported finding. See `standards/evidence.md`; `templates/adversarial-review.md` has the block.

- `product-manager`: Is the outcome worth doing now? Is the scope too broad? Are non-goals honest?
- `business-analyst`: Are users, workflows, acceptance criteria, and edge cases clear enough?
- `solution-architect`: Are capability boundaries, standards, precedent, and feasibility assumptions sound?
- Conditional roles challenge their own risk surfaces when engaged.

Adversarial review should produce dispositions:

- requirement changed
- acceptance criterion changed
- non-goal clarified
- assumption confirmed or rejected
- open question recorded
- next lane changed to `flow-solution`
- idea deferred or rejected

### Phase 5 - Requirements Capture

Capture the result in the smallest artifact that can survive handoff.

Use a structured chat summary only when all are true:

- the definition is small
- no research files were needed
- the requirements can fit clearly in one response
- no multi-session handoff is expected

Otherwise recommend and create a durable artifact using `templates/definition.md` under the run or project location that fits the work.

Required fields:

- problem or opportunity
- audience / operator / maintainer
- desired outcome
- success criteria
- acceptance criteria
- non-goals
- constraints
- assumptions
- evidence and research implications
- open questions
- approval status

### Phase 6 - Approval and Routing

Requirements are not approved until the engineer explicitly accepts them.

Routing:

- `flow-solution` when approved requirements still need technical options, architecture tradeoffs, or chunking
- `flow-plan` when the requirements and approach are clear enough to shape implementation
- further definition when evidence or scope is still incomplete
- defer/reject when the opportunity is not worth pursuing now

## Output Format

**Emit the structured output below only after discovery, research/evidence assessment, and adversarial review have completed.**

```md
## Definition Summary

### Problem or Opportunity
- What:
- Who:
- Why now:

### Desired Outcome
- [Outcome]

### Evidence
- Research needed: yes | no
- Findings and requirement implications:

### Requirements
- Success criteria:
- Acceptance criteria:
- Non-goals:
- Constraints:
- Assumptions:

### Adversarial Review
- Product:
- Requirements:
- Architecture/capability:
- Other roles:

### Artifact
- Structured chat summary | durable artifact at [path]
- Why:

### Approval
- Approved | Not approved
- Approver:
- Remaining open questions:

### Next Lane
- `flow-solution` | `flow-plan` | further definition | defer/reject
- Why:
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "We can define requirements during planning." | Planning should shape approved requirements, not discover the outcome from scratch. |
| "Research will slow us down." | Targeted research prevents requirements from hardening around guesses. |
| "The idea is obvious." | Obvious ideas still need users, outcomes, non-goals, and approval. |
| "A chat summary is enough." | Only if the requirements are small enough to survive handoff without hidden context. |
| "Adversarial review is negative." | It is how good ideas stop carrying bad assumptions. |

## Red Flags

- requirements approved without explicit user approval
- research performed without named questions
- evidence listed without implications for requirements
- no non-goals
- no acceptance criteria
- no success criteria for feature or capability value
- downstream lane chosen before adversarial review
- bug-shaped work pulled into definition instead of `flow-plan`

## Escalation Rules

- Escalate to `flow-solution` when the definition exposes multiple viable technical approaches, durable architecture decisions, or unclear capability boundaries.
- Escalate to `flow-plan` when requirements are approved and implementation shaping is the next real task.
- Stay in definition when scope, evidence, or approval is still missing.
- Defer or reject when the evidence does not justify the work.

## Verification

Before leaving `flow-define`, confirm:

- [ ] request was classified as definition-shaped
- [ ] opener role was selected intentionally
- [ ] business-analyst, product-manager, and solution-architect participated
- [ ] research need was considered explicitly
- [ ] each research finding has an implication for requirements
- [ ] adversarial review ran and findings were dispositioned
- [ ] requirements include success criteria, acceptance criteria, non-goals, constraints, assumptions, and open questions
- [ ] artifact choice was recommended and justified
- [ ] approval status is explicit
- [ ] next lane is explicit and justified

## Finish Criteria

`flow-define` is done when the user has approved requirements, or a clear reason the definition is not yet approved, and the next lane is obvious.
