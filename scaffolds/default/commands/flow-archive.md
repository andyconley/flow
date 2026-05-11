# flow-archive

Use `flow-archive` to close out a completed slice or run and convert short-lived execution into durable project memory.

## Overview

This command closes the loop on completed work. It captures what changed, what was proven, what remains risky, and what the project should remember going forward.

## When to Use

Use this command when:

- implementation and review are complete
- validation is complete enough to close the work
- a run needs a final summary, residual-risk note, and memory update

Do not use this command to decide whether work is ready. Use `flow-review` first when acceptance is still uncertain.

**When NOT to use:** before review is complete, or when the work is still actively being refined.

## Primary inputs

- the completed run or slice artifacts
- review findings and resolution status
- validation evidence
- current transient work state: `.flow/memory/STATE.md` (every stacked overlay level)
- current durable project memory at `~/.claude/projects/<project-id>/memory/` (Claude Code auto-memory — `project`-type entries)

## Primary outputs

- completion summary
- validation summary
- residual-risk and follow-up summary
- durable memory updates
- run completion marker

## Composition

Primary roles:

- `tech-writer` for durable summary and memory wording
- `quality-reviewer` when unresolved review debt needs to be summarized accurately
- `support-lead` when known operational caveats or workarounds should be preserved

The archive command does not replace review. It packages the accepted outcome.

## Archive Workflow

1. Identify the run or slice being closed.
2. Summarize what changed.
3. Record validation status:
   - tests run
   - manual checks
   - runtime or deploy checks
4. Record residual risks, follow-ups, and deferred work.
5. **Update transient work state** in `.flow/memory/STATE.md` at the **most-specific stacked overlay** (e.g., when archiving in path-nexus, writes go to `~/KB/repos/path-nexus/.flow/memory/STATE.md`, not the workspace's). STATE.md should reflect what is now in flight, blocked, or pending — not durable facts.
6. **Record durable decisions in auto-memory** at `~/.claude/projects/<project-id>/memory/`. For each cross-cutting decision worth remembering across sessions, write a structured memory file with frontmatter (`type: project`) and add a one-line entry to `MEMORY.md`. See your global CLAUDE.md auto-memory instructions for the exact format. Do NOT write decisions to `.flow/memory/` — that surface no longer exists.
7. If the work materially affects a parent overlay's state, surface that in the archive output so it can be picked up in a separate parent-level archive.
8. Mark the run complete.

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

```md
## Archive Summary

### Work Closed
- [Run or slice]
- [What changed]

### Validation
- Automated:
- Manual:
- Runtime/deploy:

### Residual Risks
- [Known caveats]

### Follow-up Work
- [Deferred or future work]

### Memory Updates
- STATE (`.flow/memory/STATE.md`): (always present; describe the transient work-state change, or "n/a — work state unchanged")
- Auto-memory entries written: (always present; list new or updated auto-memory files by name + one-line summary, or "n/a — no durable decisions recorded")
- Parent-overlay implications: (only if changes here affect a higher overlay)
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "The code is merged, so archive is unnecessary." | Merge is not memory. Archive is what makes the outcome durable. |
| "Residual risks are obvious from the diff." | Risks disappear quickly unless they are written down explicitly. |
| "We can update STATE and auto-memory later." | Later is usually never; archive is the right time to make memory durable. |
| "STATE.md and auto-memory hold the same kind of thing." | They do not — STATE.md is transient work state at the project; auto-memory holds durable cross-session facts and decisions. Mixing them defeats both. |

## Red Flags

- no explicit validation status
- memory updates omitted
- follow-up work implied but not listed
- archive summary is just a changelog dump

## Verification

Before leaving `flow-archive`, confirm:

- [ ] what changed is summarized clearly
- [ ] validation status is explicit
- [ ] residual risks and follow-up work are explicit
- [ ] STATE.md was updated (or explicitly marked "n/a")
- [ ] durable decisions were written to auto-memory (or explicitly marked "n/a — no durable decisions recorded")
- [ ] writes went to the most-specific overlay; parent-overlay implications surfaced if applicable
- [ ] the run is clearly marked complete

## Finish Criteria

`flow-archive` is done when:

- the closed work is summarized clearly
- validation status is explicit
- durable memory reflects the new reality
- remaining risks are recorded rather than implied
