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

Synthesize across:

- the CLAUDE.md context already loaded for the session (user → workspace → project levels)
- the framework operating model (provided via the session-start hook)
- `/tmp/session_checkpoint.md` if present (within-session continuity from a prior compaction)

Read explicitly from every stacked overlay level (most-specific to most-general):

- `.flow/PROJECT.md`
- `.flow/memory/STATE.md`
- `.flow/memory/DECISIONS.md`

Inspect:

- `.flow/runs/` from every stacked overlay level

## Primary outputs

- current orientation summary
- active or interrupted work summary
- current sources of truth (including which overlay level provides which)
- recommended next command

## Boot Workflow

1. Synthesize the CLAUDE.md context already loaded (user, workspace, project) and the session-start hook's framework context.
2. Read `/tmp/session_checkpoint.md` if present.
3. Read project overlay files from every stacked overlay level (most-specific to most-general): PROJECT.md, memory/STATE.md, memory/DECISIONS.md. Merge with more-specific overriding on conflicts.
4. Check for interrupted or active runs across all stacked overlay levels.
5. Identify:
   - the project's operating model and any project-specific role assignments
   - the active standards and overlays that matter right now
   - active or interrupted work
   - memory caveats, blockers, or migration notes
6. Recommend the next command:
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

- [ ] CLAUDE.md context across user/workspace/project was synthesized
- [ ] `/tmp/session_checkpoint.md` was read if present
- [ ] PROJECT.md and memory were read across all stacked overlay levels
- [ ] interrupted or active runs were checked across all stacked overlay levels
- [ ] the next recommended command is explicit

## Finish Criteria

`flow-boot` is done when the next step is obvious and the current durable context is unambiguous.
