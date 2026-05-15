# flow-plan

Use `flow-plan` for shaping work before implementation starts.

<HARD-GATE>
Do NOT produce the Plan Summary, define scope boundaries, specify contracts, or recommend a lane until you have completed the Engagement Phase: restated the problem in your own words, surfaced your explicit unknowns, and the engineer has confirmed your understanding. This applies regardless of how well-specified the request seems. A confidently-drafted plan built on inferred context is worse than asking and being told.
</HARD-GATE>

## Overview

This command turns a request into an implementation-ready plan. It exists to remove hidden context, tighten scope, define proof, and choose the right execution lane before code starts.

The command runs in **three explicit phases**: Engagement (dialogue to confirm the problem) → Shaping (scope, states, contracts, validation) → Capture (emit the Plan Summary). The phases are gated; do not collapse them into a single response.

## When to Use

Use this command to:

- turn an idea, bug, or request into an implementation-ready work item
- define scope boundaries
- identify required states and contracts
- define validation expectations
- decide whether the work belongs in `flow-scout` or `flow-implement`

If the work cannot be understood without chat history, the plan is not done yet.

**When NOT to use:** trivial, obvious XS changes that already fit cleanly inside `flow-scout`, or post-implementation review work that belongs in `flow-review`.

## Primary inputs

- feature idea, bug, request, or initiative
- relevant project context
- existing standards and overlays
- any current discovery or support evidence

## Primary outputs

- problem statement
- scoped implementation-ready plan
- required states and contracts
- validation expectations
- next-lane recommendation

## Composition

Core roles (always invoked):

- `business-analyst` for problem framing and acceptance criteria
- `product-manager` for scope and prioritization discipline
- `architect` for solution shape and structural fit

Conditional roles (invoked by the core trio when relevant):

- `ux-specialist` when user-facing states or interaction contracts matter
- `test-engineer` when proof expectations need explicit shaping beyond the default

`flow-plan` is the command that makes a task buildable without relying on invisible context.

## Planning Workflow

### Phase 1 — Engagement

Open with dialogue. Do not produce the Plan Summary, scope boundaries, contracts, or a lane recommendation in this phase.

**Scope check (do this first).** If the request describes multiple independent work items or an obviously-multi-slice initiative that needs decomposing before a single plan can shape it, flag this immediately. Don't spend questions refining scope of a problem that needs to be split first. Help the engineer decompose, and ask which sub-problem they want to plan first.

For appropriately-scoped problems, your first reply must contain three things and only these things:

1. **Restated problem** — describe what you understand the engineer is trying to solve, in your own words. Cover *what / who / why now* explicitly. Not a quote of the request — a translation.
2. **Explicit unknowns** — list what you DON'T yet know. Surface gaps in scope, success criteria, required states, contract shape, validation expectations, and any assumptions you'd need to verify. "I'm assuming X" is more useful than confidently asserting X.
3. **Clarifying questions** — 3 to 5 specific questions whose answers would close the highest-impact unknowns. Prefer multiple-choice or yes/no over open-ended when possible. Ask **one question at a time** if you anticipate the answer will reshape the next question; otherwise group a small set.

**Hard checkpoint.** Do not proceed to Phase 2 until the engineer has confirmed your problem statement and answered enough of the questions that the unknowns are reduced to manageable. Returning to Phase 1 mid-engagement is allowed and expected.

### Phase 2 — Shaping

Only enter this phase after the Phase 1 hard checkpoint passes.

1. Define desired outcome.
2. Define in-scope and out-of-scope items.
3. Identify required states when UI is involved:
   - loading
   - empty
   - error
   - success
   - confirmation
4. Define contract expectations for whichever apply to this work:
   - UI/UX contract (states, interaction patterns, accessibility)
   - API shape (request/response, error envelope)
   - data shape (schema, invariants, migration concerns)
   - workflow contract (events, transitions, idempotency)
   - document structure (sections, audience, level of detail)
   - other contract types as relevant
5. Define validation expectations.

### Phase 3 — Capture

Only enter this phase after Phase 2's shaping work is complete and the engineer has either accepted it or fed back adjustments.

1. **Capture.** Emit the Plan Summary (template below).
2. **Recommend the lane.** `flow-scout` or `flow-implement`, with rationale.

## Output Format

**Emit the structured output below only in Phase 3 — after the engagement and shaping phases have completed.** Do not produce this template in your first reply to the engineer.

```md
## Plan Summary

### Problem Statement
- What:
- Who:
- Why now:

### Desired Outcome
- [Outcome]

### Scope
- In scope:
- Out of scope:

### States and Contracts
- Required states:
- Contract expectations:

### Validation
- [How the work will be proven]

### Recommended Lane
- `flow-scout` | `flow-implement`
- Why:
```

## Anti-Pattern: Skipping the Engagement

Every planning run goes through the Engagement Phase. A "simple" or "well-specified" request is *exactly* where unexamined assumptions cause the most wasted planning work. The dialogue can be short (a single round of confirmation for genuinely well-specified problems), but you MUST produce the restate-unknowns-questions reply and the engineer MUST confirm before any scope, contracts, or lane recommendation is drafted.

The most common failure mode of this command is jumping straight to scope and contracts because the request *looks* clear. Resist it. A plan built on inferred context produces wrong scope, wrong contracts, or a wrong lane recommendation — all of which propagate into wrong implementation.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I have enough context from the request to draft a plan." | Planning starts with what you DON'T know, not what you can infer. If you didn't have to ask anything, you skipped the work. |
| "The problem is well-specified; I don't need to clarify." | Specified ≠ unambiguous. Your restated version may differ from the engineer's intent in ways neither of you would catch without saying it out loud. |
| "I'll ask questions as they come up while drafting." | The engineer should answer questions before the plan exists, not be cornered into accepting one because it's already drafted. |
| "The scope is obvious; we can just start coding." | Hidden scope is exactly what causes drift and rework. Write the plan down. |
| "We'll figure out validation later." | If proof is undefined, the work is not implementation-ready. |
| "This only affects UI; we don't need to define states." | Missing state definitions are a common source of broken UX and review churn. |
| "The task is small enough that chat history is fine." | If the task cannot survive session boundaries, the plan is incomplete. |

## Red Flags

- proceeding to Phase 2 (shaping) before the engineer has confirmed the problem statement
- first reply contains the Plan Summary template, scope boundaries, or a lane recommendation
- restating without surfacing explicit unknowns or questions
- producing the structured output template in a single reply
- plan depends on unstated chat context
- no in-scope / out-of-scope boundary
- no validation strategy
- UI work without explicit states
- lane recommendation is absent or hand-wavy

## Escalation Rules

- Escalate to `flow-scout` if the work is truly narrow and self-contained.
- Escalate to `flow-implement` if it spans multiple files, sessions, states, or decision surfaces.
- Do not let implementation start until the plan is understandable without private chat context.

## Verification

Before leaving `flow-plan`, confirm:

- [ ] Phase 1 happened — first reply was restate + unknowns + questions; no scope or contracts drafted yet
- [ ] engineer confirmed the problem statement before Phase 2 began
- [ ] the problem statement is explicit
- [ ] in-scope and out-of-scope items are listed
- [ ] required states and contracts are identified when relevant
- [ ] validation expectations are defined
- [ ] the recommended lane is clear and justified
- [ ] another engineer or agent could implement from the plan alone

## Finish Criteria

`flow-plan` is done when another engineer or agent can implement the work from the plan alone.
