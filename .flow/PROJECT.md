# Flow Project Overlay

## Summary

- Project name: flow
- Project type: Python CLI and portable workflow framework
- Primary runtime: Claude and Codex
- Short description: Runtime-neutral workflow contracts, role agents, lifecycle state, adapters, standards, and templates.

## Role providers

- Product owner: repository owner
- Product manager: Flow product-manager role or main orchestrator
- Requirements shaping: Flow business-analyst role with engineer approval
- Implementation: Flow lead-developer role or main coding agent
- Acceptance review: Flow quality-reviewer and test-engineer roles; independent provider when risk requires it

## Collaboration deviations and tightening

- Additional ready-for-implementation gates: approved C-Lite plan, implementation handoff, and validation plan
- Review-only rules: acceptance review does not silently implement fixes
- Queue or status conventions: `.flow/runs/<work-id>/run.json` is the lifecycle projection
- Escalation triggers: runtime contract changes, lifecycle compatibility, generated-adapter drift, or release risk

## Sources of truth

1. Repository issue or explicitly approved work item
2. This file
3. ADRs and approved run artifacts
4. Code and tests
5. `.flow/memory/STATE.md`
6. Active runtime memory provider, when one exists

Framework standards and templates come from the installed Flow source and are not copied into this overlay.

## Workflow notes

- Preferred small-change path: `flow-scout`
- Preferred gated-work path: define or plan, implement, review, archive
- Escalate when work spans runtime contracts, lifecycle state, generated surfaces, or release behavior

## Runtime and integration notes

- External systems: GitHub repository, Actions, tags, and releases
- Deployment environment: user-level Claude and Codex runtime adapters
- Testing/deploy constraints: Python standard-library CLI, cross-runtime generated-surface checks, semantic-release on `main`
