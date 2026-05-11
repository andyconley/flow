# flow-status

Use `flow-status` to summarize the current project execution state.

## Overview

This command provides a concise current-state readout so a collaborator can understand what is active, what is blocked, and what should happen next.

## When to Use

Use this when the question is:

- where are we?
- what is active?
- what should happen next?

This is a state-summary command, not a shaping or implementation command.

**When NOT to use:** when the real need is to plan new work, resume an interrupted run in detail, or review implementation quality.

## Primary inputs

- `.flow/runs/`
- `.flow/memory/STATE.md`
- `.flow/memory/DECISIONS.md`
- current project overlays when needed

## Primary outputs

- active or recent run summary
- current memory highlights
- important blockers or caveats
- recommended next command

## Status Workflow

1. Identify active or recent runs at the current project level. Note any active runs at parent overlay levels separately as parent context (do not conflate them with the project's own state).
2. Read current memory highlights from all stacked overlay levels. Surface project-level highlights prominently; parent-overlay highlights appear under a separate parent-context heading.
3. Summarize blockers, caveats, or unresolved decisions.
4. Recommend the next command based on the real current state.

## Output Format

```md
## Status Summary

### Active or Recent Work
- [Runs / slices at current project level]

### Memory Highlights
- [Important state / decisions at current project level]

### Parent Workspace Context (if applicable)
- [Active runs or notable state at parent overlay levels — surface but do not conflate]

### Blockers or Caveats
- [Current issues]

### Recommended Next Command
- [Command and why]
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I'll just infer the current state from memory." | Status exists because active work and durable memory drift apart. |
| "Recent work is enough; we don't need blockers." | A status readout without blockers is only half-useful. |
| "The next command is obvious." | If it isn't written down, collaborators often diverge. |

## Red Flags

- recent runs listed without any interpretation
- memory highlights omitted
- blockers or caveats hidden in prose
- no next-step recommendation

## Verification

Before leaving `flow-status`, confirm:

- [ ] active or recent work is summarized
- [ ] memory highlights are included
- [ ] blockers or caveats are explicit
- [ ] the next recommended command is explicit

## Finish Criteria

`flow-status` is done when a collaborator can tell where the project stands and what should happen next.
