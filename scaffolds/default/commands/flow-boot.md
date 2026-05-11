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
8. **Overlay-setup check.** If the current project (cwd's git repo) has no `.flow/` overlay:
   - Check for an explicit opt-out marker `.flow-skip` at the project root.
   - If `.flow-skip` exists, treat the absence as **"by design"** — the user has explicitly opted out. Do not recommend setup.
   - Otherwise, **recommend `flow setup project`**. Default to recommending — do not qualify it as "optional" or speculate that "this project doesn't need one." If the user wants to opt out for this repo, they can `touch .flow-skip` at the root; until that marker exists, recommend setup.
9. Recommend the next command. Candidates depend on state. **Distinguish slash commands (invoked inside Claude as `/flow-XXX`) from CLI commands (run from the shell or asked of Claude):**
   - `flow setup project` *(shell command — ask Claude to run it, or run it yourself from a terminal at the repo root)* — if no overlay exists and no `.flow-skip` marker is present
   - `/flow-status` — if active work is unclear
   - `/flow-resume` — if there is interrupted work to continue
   - `/flow-plan` — if new work needs shaping
   - `/flow-scout` — for small in-flight changes
   - `/flow-implement` — for gated work already shaped

   **When recommending `flow setup project`, the output must:**
   - **Make it clear this is a shell command, not a slash command** — the user types `/flow-boot` to invoke a skill, but `flow setup project` is invoked via shell. The user can just ask Claude to run it (Claude has Bash), or run it themselves from a terminal at the repo root.
   - **Surface the opt-out as a parallel option**: the user can tell Claude to opt out, at which point Claude `touch .flow-skip` at the repo root. The user may also run that shell command themselves.

   Phrase both options so the user knows they can simply *ask* — they don't need to context-switch to a terminal for either path. This pairing keeps the recommendation strong-by-default without nagging users who have decided flow's overlay isn't right for a particular repo.

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

```md
## Project Orientation

### Context
- Project:
- Current focus:
- Overlay status: (one of: "active at <path>" | "absent — flow setup project recommended" | "absent — by design (.flow-skip marker present)")

### Active Memory
- [Important STATE highlights + relevant auto-memory entries]

### Active or Interrupted Work
- [Run or slice summaries; "none active" if clean]

### Session Checkpoint
- [Status: "current" | "superseded by commits since <date> — safe to discard" | "no checkpoint present"]

### Sources of Truth
- [Files that matter right now]

### Recommended Next Command
- [Command and why — write slash commands as `/flow-XXX` and CLI commands as `flow XXX YYY` (shell)]
- (If recommending `flow setup project`, the output must also clarify: "`flow setup project` is a shell command, not a slash command — ask me to run it, or run it yourself from a terminal at the repo root.")
- (If recommending `flow setup project`, also surface the opt-out: "Or to silence this recommendation: tell me to opt out (I'll `touch .flow-skip` at the repo root). You can also run that shell command yourself if you prefer.")
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
- [ ] overlay status was reported; `.flow-skip` marker was checked before classifying "by design"; default for missing overlay is "recommended", not "by design"
- [ ] the next recommended command is explicit

## Finish Criteria

`flow-boot` is done when the next step is obvious and the current durable context is unambiguous.
