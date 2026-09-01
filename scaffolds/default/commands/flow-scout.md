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

## C-Lite Run Protocol

Scout does not create a run envelope at start. If scout work grows out of scout
criteria, stop and create a linked core-path run from a scout summary:

```bash
flow run transition <work-id> start-definition \
  --artifact scout_summary=.flow/runs/<work-id>/scout-summary.md
```

If scout work completes and is archived without escalation, create only the
minimal closure envelope:

```bash
flow run transition <work-id> archive-scout \
  --artifact scout_summary=.flow/runs/<work-id>/scout-summary.md \
  --disposition capability_gaps=<recorded|n/a> \
  --disposition memory=<updated|n/a>
```

## Orchestration safety

Ordinary scouts remain lightweight. If a scout delegates or mutates shared external state, follow `standards/orchestration.md`, create the canonical manifest, run `flow run validate-orchestration <work-id> --stage dispatch` before the action, and pass `--artifact orchestration_manifest=.flow/runs/<work-id>/orchestration.json` to `archive-scout`; closure conditionally validates acceptance.

## Scout-Size Criteria

A change qualifies for scout mode when ALL of the following hold:

- **Single primary file** — incidental edits to imports, an adjacent test, or one supporting file are fine
- **No new abstractions, interfaces, or data shapes**
- **No new UI states** — no new loading/empty/error states; existing patterns only
- **Validation completes within 5 minutes** of focused effort

If any criterion fails, do not start scout. Escalate to `flow-plan` to shape the work first.

`flow-scout` should stay narrow and should not silently turn into full implementation mode.

## Scout Workflow

1. **Hard checkpoint:** verify the change meets ALL Scout-Size Criteria. If any criterion fails, stop and route to `flow-plan` — do NOT continue in scout mode.
2. Identify the narrowest possible change surface.
3. Make the focused change.
4. **Mid-flight check:** if any Scout-Size Criterion stops holding (e.g., the change is touching a second primary file, a new abstraction is forming, validation is running long), stop and route to `flow-plan` with what you've learned. Do not silently continue.
5. Validate at the smallest sufficient level.
6. **Commit per Conventional Commits.** A scout change is a single logical commit; use the message format defined in `standards/git-commits.md` (type prefix required; `fix`/`docs`/`test`/`refactor`/`chore` are the most common types in scout mode).
7. Return concise handback.

## Rules

- keep scope narrow
- avoid architectural drift
- do not widen requirements
- escalation is mandatory, not advisory: if Scout-Size Criteria fail at any point, stop and route to `flow-plan`

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

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

- [ ] Scout-Size Criteria were verified at the start and held throughout
- [ ] the scope stayed narrow
- [ ] the validation is proportionate and explicit
- [ ] no hidden architecture or requirement changes were introduced
- [ ] the handback is concise but complete

## Finish Criteria

`flow-scout` is done when a narrow change is completed, validated, and handed back without accumulating hidden complexity.
