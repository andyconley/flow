# flow-plan

Use `flow-plan` for shaping work before implementation starts.

## Overview

This command turns a request into an implementation-ready plan. It exists to remove hidden context, tighten scope, define proof, and choose the right execution lane before code starts.

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

Primary roles:

- `business-analyst` for problem framing and acceptance criteria
- `product-manager` for scope and prioritization discipline
- `ux-specialist` when user-facing states or interaction contracts matter
- `architect` when the shape of the solution materially affects scope
- `test-engineer` for proof expectations

`flow-plan` is the command that makes a task buildable without relying on invisible context.

## Planning Workflow

1. State the problem clearly:
   - what
   - who
   - why now
2. Define desired outcome.
3. Define in-scope and out-of-scope items.
4. Identify required states when UI is involved:
   - loading
   - empty
   - error
   - success
   - confirmation
5. Define contract expectations:
   - Storybook
   - API
   - data
   - workflow
6. Define validation expectations.
7. Recommend:
   - `flow-scout`
   - `flow-implement`

## Output Format

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

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "The scope is obvious; we can just start coding." | Hidden scope is exactly what causes drift and rework. Write the plan down. |
| "We'll figure out validation later." | If proof is undefined, the work is not implementation-ready. |
| "This only affects UI; we don't need to define states." | Missing state definitions are a common source of broken UX and review churn. |
| "The task is small enough that chat history is fine." | If the task cannot survive session boundaries, the plan is incomplete. |

## Red Flags

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

- [ ] the problem statement is explicit
- [ ] in-scope and out-of-scope items are listed
- [ ] required states and contracts are identified when relevant
- [ ] validation expectations are defined
- [ ] the recommended lane is clear and justified
- [ ] another engineer or agent could implement from the plan alone

## Finish Criteria

`flow-plan` is done when another engineer or agent can implement the work from the plan alone.
