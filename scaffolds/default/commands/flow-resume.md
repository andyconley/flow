# flow-resume

Use `flow-resume` to pick up interrupted work.

## Overview

This command reconstructs the state of interrupted execution so work can continue without guessing or restarting unnecessarily.

## When to Use

Use this command when:

- there is an interrupted run
- a session ended mid-slice
- the current state of execution is unclear but a fresh start would lose useful artifacts

**When NOT to use:** when there is no meaningful prior run to continue, or when the previous attempt is clearly obsolete and should be superseded intentionally.

## Primary inputs

- `.flow/runs/` (every stacked overlay level — most-specific first)
- `.flow/memory/STATE.md` — transient work state at every stacked overlay level
- active runtime memory provider, when one exists — relevant durable facts/decisions
- latest run artifacts and notes

## Primary outputs

- identified run to resume
- last completed phase
- current blocker or next step
- recommended continuation lane

## C-Lite Run Protocol

Resume canonical run state before inferring from artifacts:

```bash
flow run status <work-id>
flow run verify <work-id>
```

If `run.json` is absent, report the selected run as `legacy/inferred` and say
which artifacts support the inference. Do not write C-lite state as a side
effect of resume.

## Guiding Principle

`flow-resume` should prefer continuity over restart unless the old run is clearly obsolete.

## Resume Workflow

1. Locate the most relevant interrupted run. Search the **most-specific overlay first**; fall back to broader stacked overlay levels only if no runs are present locally.
2. Identify the last completed phase.
3. Restate:
   - current blocker
   - next step
   - missing evidence or missing artifacts
4. Recommend whether to continue in:
   - scout mode
   - gated implementation
5. Continue the existing artifact chain unless starting fresh is clearly safer.
6. Treat project artifacts and C-lite run state as canonical. Runtime memory is
   companion context: read Claude Code auto-memory when available; do not treat
   missing Codex durable memory as missing workflow state.

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

```md
## Resume Summary

### Selected Run
- [Run identifier]

### Last Completed Phase
- [Phase]

### Current State
- Blocker:
- Next step:
- Missing artifacts or evidence:

### Recommended Continuation
- `flow-scout` | `flow-implement`
- Why:
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "It's easier to start over." | Restarting often throws away useful artifact chains and hides prior decisions. |
| "The last phase is obvious from memory." | Resume exists because memory is usually incomplete. |
| "The missing artifact probably doesn't matter." | Missing evidence often explains why the work stopped. |

## Red Flags

- selected run is not justified
- last completed phase is unclear
- next step is guessed rather than derived
- missing artifacts are ignored instead of called out

## Verification

Before leaving `flow-resume`, confirm:

- [ ] the correct interrupted run was identified (most-specific overlay searched first, broader as fallback)
- [ ] the last completed phase is explicit
- [ ] the blocker or next step is explicit
- [ ] the continuation lane is justified

## Finish Criteria

`flow-resume` is done when the team can continue from the interrupted work without re-deriving context.
