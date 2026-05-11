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
2. Project standards in `.flow/project/`
3. ADRs
4. Code
5. `.flow/memory/STATE.md` (transient work state — what is in flight, blocked, or pending right now)
6. Claude Code auto-memory at `~/.claude/projects/<project-id>/memory/` (durable project facts and decisions)

## Active project standards

- `project/brand.md`
- `project/domain-model.md`
- `project/ux-guide.md`
- `project/copy-guide.md`
- `project/terminology.md`
- `project/ui-contract.md`

These project files should augment or tighten the base framework standards with repo-specific rules, domain concepts, design language, and platform constraints.

## Workflow notes

- Preferred small-change path:
- Preferred gated-work path:
- When to escalate from scout to plan or implement:

## Runtime and integration notes

- external systems:
- deployment environment:
- testing/deploy constraints:
