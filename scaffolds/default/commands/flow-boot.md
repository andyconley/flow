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
- durable facts and decisions in Claude Code auto-memory at `~/.claude/projects/<project-id>/memory/` (read `MEMORY.md` as the index)

Read explicitly from every stacked overlay level (most-specific to most-general):

- `.flow/PROJECT.md`
- `.flow/memory/STATE.md` (transient work state only — durable facts live in auto-memory)

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
3. **Freshness check the session checkpoint.** If `/tmp/session_checkpoint.md` exists, compare its "Files modified this session" / "Tasks completed" lists against `git log --stat` since the checkpoint's date. If commits since that date cover the checkpoint's work, treat the checkpoint as **superseded** rather than interrupted, and recommend discarding it in the output.
4. Read project overlay files from every stacked overlay level (most-specific to most-general): `PROJECT.md` and `memory/STATE.md`. Merge with more-specific overriding on conflicts.
5. Read the auto-memory index at `~/.claude/projects/<project-id>/memory/MEMORY.md` and pull in any entries relevant to the current focus.
6. Check for interrupted or active runs across all stacked overlay levels.
7. Identify:
   - the project's operating model and any project-specific role assignments
   - the active standards and overlays that matter right now
   - active or interrupted work
   - memory caveats, blockers, or migration notes
8. **Overlay-setup check.** If the current project (cwd's git repo) has no `.flow/` overlay AND substantial work happens here, recommend `flow setup project` as a candidate next command. Phrase it as an option, not a mandate — many projects don't need an overlay.
9. Recommend the next command. Candidates depend on state:
   - `flow setup project` — if no overlay exists and one would help
   - `flow-status` — if active work is unclear
   - `flow-resume` — if there is interrupted work to continue
   - `flow-plan` — if new work needs shaping
   - `flow-scout` — for small in-flight changes
   - `flow-implement` — for gated work already shaped

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

```md
## Project Orientation

### Context
- Project:
- Current focus:
- Overlay status: (one of: "active at <path>" | "absent — flow setup project recommended" | "absent — project is light, no overlay needed")

### Active Memory
- [Important STATE highlights + relevant auto-memory entries]

### Active or Interrupted Work
- [Run or slice summaries; "none active" if clean]

### Session Checkpoint
- [Status: "current" | "superseded by commits since <date> — safe to discard" | "no checkpoint present"]

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
- [ ] checkpoint freshness was checked against `git log` since its date (when checkpoint exists)
- [ ] PROJECT.md and STATE.md were read across all stacked overlay levels
- [ ] auto-memory MEMORY.md was consulted for relevant durable facts/decisions
- [ ] interrupted or active runs were checked across all stacked overlay levels
- [ ] overlay status was reported in the output (active / absent-with-recommendation / absent-by-design)
- [ ] the next recommended command is explicit

## Finish Criteria

`flow-boot` is done when the next step is obvious and the current durable context is unambiguous.
