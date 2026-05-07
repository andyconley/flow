# flow-boot

Use `flow-boot` to orient to the project before planning or implementation work.

## Overview

This command establishes current context before action. It reduces mistakes caused by stale memory, interrupted work, or hidden source-of-truth shifts.

## When to Use

Use this command:

- at the start of a session
- before resuming interrupted work
- when project context feels stale, split, or ambiguous

**When NOT to use:** as a substitute for planning, implementation, or review. Boot is for orientation only.

## Primary inputs

Read at minimum:

- `.flow/FRAMEWORK.md`
- `.flow/PROJECT.md`
- `.flow/memory/STATE.md`
- `.flow/memory/DECISIONS.md`

Inspect:

- `.flow/runs/`

## Primary outputs

- current orientation summary
- active or interrupted work summary
- current sources of truth
- recommended next command

## Composition

Primary roles:

- `business-analyst` for reading intent and current work context
- `tech-writer` for identifying durable source-of-truth documents
- `support-lead` when interrupted work or operational caveats need triage

`flow-boot` should orient, not re-plan the project.

## Boot Workflow

1. Read the framework and project overlays.
2. Read current durable memory.
3. Check for interrupted or active runs.
4. Identify:
   - the project’s operating model
   - the active standards and overlays that matter right now
   - active or interrupted work
   - memory caveats, blockers, or migration notes
5. Recommend the next command:
   - `flow-status`
   - `flow-resume`
   - `flow-plan`
   - `flow-scout`
   - `flow-implement`

## Output Format

```md
## Project Orientation

### Context
- Project:
- Current focus:

### Active Memory
- [Important STATE / DECISIONS highlights]

### Active or Interrupted Work
- [Run or slice summaries]

### Sources of Truth
- [Files that matter right now]

### Recommended Next Command
- [Command and why]
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I remember the project well enough." | Memory drift is exactly what boot is designed to correct. |
| "The runs directory probably hasn't changed." | Interrupted or parallel work is easy to miss without checking. |
| "I'll just start coding and re-orient if needed." | Re-orienting after implementation begins is slower and riskier. |

## Red Flags

- no explicit source-of-truth list
- interrupted work is ignored
- memory files are not read
- next command recommendation is vague or absent

## Verification

Before leaving `flow-boot`, confirm:

- [ ] current framework and project overlays were read
- [ ] durable memory was reviewed
- [ ] interrupted or active runs were checked
- [ ] the next recommended command is explicit

## Finish Criteria

`flow-boot` is done when the next step is obvious and the current durable context is unambiguous.
