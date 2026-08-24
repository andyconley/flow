# Project Overlay

## Summary

- Project name:
- Project type:
- Primary runtime:
- Short description:

## Role providers

- Product owner:
- Product manager:
- Requirements shaping:
- Implementation:
- Acceptance review:

## Collaboration deviations and tightening

- Additional ready-for-implementation gates:
- Review-only rules:
- Queue or status conventions:
- Escalation triggers:

## Sources of truth

1. Ticket / issue tracker
2. This file
3. ADRs
4. Code
5. `.flow/memory/STATE.md` (transient work state — what is in flight, blocked, or pending right now)
6. Active runtime memory provider, when one exists (durable project facts and decisions; Claude Code uses auto-memory at `~/.claude/projects/<project-id>/memory/`; Codex currently has no Flow-managed durable provider)

Standards and templates are not among them: they come from the user-level
install, not from this overlay. Record here what is true of *this* project —
its domain language, its constraints, its conventions — and let the framework
supply the rest.

## Workflow notes

- Preferred small-change path:
- Preferred gated-work path:
- When to escalate from scout to plan or implement:

## Runtime and integration notes

- external systems:
- deployment environment:
- testing/deploy constraints:
