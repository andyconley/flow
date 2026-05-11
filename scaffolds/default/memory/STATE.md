# Current State

This file holds **transient work state** for this project — what is in flight right now, what is blocked, what to pick up next session. It is **not** a store of durable facts or decisions; those go to Claude Code's auto-memory at `~/.claude/projects/<project-id>/memory/`.

## What belongs here

- the latest meaningful in-progress or recently completed work
- active blockers and caveats
- next-session orientation notes
- ephemeral "where am I in this multi-phase run" markers

## What does NOT belong here

- durable project facts → write to auto-memory (`project` type)
- decisions about how the project works → write to auto-memory (`project` type)
- user preferences or feedback → write to auto-memory (`user` or `feedback` type)
- pointers to external systems → write to auto-memory (`reference` type)

## When to update

- at the end of an implementation run via `flow-archive`
- when blockers shift mid-run
- whenever active work state changes in a way the next session would need to know

## Scope rule

When this file lives in a stacked overlay structure (e.g., both `~/KB/.flow/memory/STATE.md` and `~/KB/repos/path-nexus/.flow/memory/STATE.md`), each holds only the work state at that overlay's level. Writes always go to the **most-specific** overlay.
