# Current State

This file holds **transient work state** for this project — what is in flight right now, what is blocked, what to pick up next session. It is **not** durable decision authority. Canonical evidence lives in lifecycle-backed run artifacts, archive envelopes and declarations, and ADRs. A runtime memory provider may retain companion recall when one exists.

## What belongs here

- the latest meaningful in-progress or recently completed work
- active blockers and caveats
- next-session orientation notes
- ephemeral "where am I in this multi-phase run" markers

## What does NOT belong here

- durable decision evidence → preserve it in the relevant run artifact, archive envelope/declaration, or ADR
- decisions about how the project works → record them in an ADR or other accepted project artifact
- user preferences or feedback → record them in the owning project artifact; optionally copy a concise reminder to companion runtime memory
- durable external references → record them in the artifact whose claim they support

Claude Code's provider is auto-memory at `~/.claude/projects/<project-id>/memory/`.
Codex currently has no Flow-managed durable memory provider. In either runtime,
companion memory may aid recall but cannot replace canonical evidence.

## When to update

- at the end of an implementation run via `flow-archive`
- when blockers shift mid-run
- whenever active work state changes in a way the next session would need to know

## Scope rule

When this file lives in a stacked overlay structure (e.g., both `~/KB/.flow/memory/STATE.md` and `~/KB/repos/path-nexus/.flow/memory/STATE.md`), each holds only the work state at that overlay's level. Writes always go to the **most-specific** overlay.
