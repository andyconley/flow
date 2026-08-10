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

- `.flow/runs/` (every stacked overlay level)
- `.flow/memory/STATE.md` — transient work state at every stacked overlay level
- Claude Code auto-memory at `~/.claude/projects/<project-id>/memory/` — durable project facts and decisions; read `MEMORY.md` as the index
- current project overlays when needed

## Primary outputs

- active or recent run summary
- current memory highlights
- important blockers or caveats
- recommended next command

## Status Workflow

1. Identify active or recent runs at the current project level. Note any active runs at parent overlay levels separately as parent context (do not conflate them with the project's own state).
2. Read current transient work state from STATE.md across stacked overlay levels. Surface project-level prominently; parent-overlay state appears under a separate parent-context heading.
3. Pull any auto-memory entries relevant to the current focus (from `~/.claude/projects/<project-id>/memory/`). Mention them when they affect the current state readout.
4. Summarize blockers, caveats, or unresolved decisions.
5. **Session cost (informational only — never a blocker, never changes the next-command recommendation by itself).** Run `flow cost active` and identify the current session: match on this project's cwd — it is typically the least-idle row. If the match is ambiguous (several rows share the cwd), say so and show the candidates rather than guessing. Report the matched row's ctx/carry and the tool's recommendation as information; the user decides. The store has no concept of a run, so this is deliberately the *session's* cost, not the run's — say "this session," not "this run." If `flow` or the usage store is unavailable, skip this step silently.
6. Recommend the next command based on the real current state.

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

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

### Session Cost (omit the section entirely when the store has nothing for this session)
- [This session's ctx/carry and the tool's recommendation — informational, the user decides]

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
- [ ] the session-cost check ran (`flow cost active`) — reported when the store had this session, silent when it didn't, ambiguity said aloud rather than guessed
- [ ] the next recommended command is explicit

## Finish Criteria

`flow-status` is done when a collaborator can tell where the project stands and what should happen next.
