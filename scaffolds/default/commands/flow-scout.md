# flow-scout

Use `flow-scout` for XS/S changes that do not justify a full gated run.

## Overview

This command is for small, narrow work that should move quickly without pulling in the full gated implementation machinery. It protects speed by protecting scope.

## When to Use

Good fits:

- single-file fixes
- copy or terminology corrections
- focused test improvements
- small UI polish on an established pattern

Do not use scout mode when the task grows into architecture, cross-session execution, or significant behavior shaping.

**When NOT to use:** anything with unclear requirements, large blast radius, multiple user-facing states, or durable execution artifacts.

## Primary inputs

- small scoped request
- relevant local code or docs
- applicable standards or project overlays

## Primary outputs

- focused change
- focused validation
- concise handback

## Composition

Primary roles:

- `lead-developer` for small technical changes
- `tech-writer` for copy or terminology fixes
- `test-engineer` for targeted proof updates
- `ux-specialist` for small polish on established patterns

`flow-scout` should stay narrow and should not silently turn into full implementation mode.

## Scout Workflow

1. Confirm the change is small enough for scout mode.
2. Identify the narrowest possible change surface.
3. Make the focused change.
4. Validate at the smallest sufficient level.
5. Return concise handback.

## Rules

- keep scope narrow
- avoid architectural drift
- do not widen requirements
- escalate to `flow-plan` or `flow-implement` if the task grows

## Output Format

```md
## Scout Summary

### Scope
- [What changed]

### Validation
- [What was checked]

### Handback
- [Outcome]
- [Any caveats]
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "It's probably still small enough." | If you're unsure, the scope is already drifting. Re-evaluate the lane. |
| "I'll just sneak in this adjacent cleanup." | Scout mode works because it stays narrow. Adjacent cleanup is usually scope creep. |
| "This won't need documentation or handback." | Even small changes need concise proof and handback. |
| "It touches multiple states, but it's still quick." | State-heavy work usually belongs in planning or gated implementation. |

## Red Flags

- touching multiple unrelated files without a clear narrow reason
- changing behavior beyond the stated request
- discovering missing requirements mid-change
- scout summary is longer than the change itself
- repeated temptation to "also fix" nearby issues

## Verification

Before leaving `flow-scout`, confirm:

- [ ] the scope stayed narrow
- [ ] the validation is proportionate and explicit
- [ ] no hidden architecture or requirement changes were introduced
- [ ] the handback is concise but complete

## Finish Criteria

`flow-scout` is done when a narrow change is completed, validated, and handed back without accumulating hidden complexity.
