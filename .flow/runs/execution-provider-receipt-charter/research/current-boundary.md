# Research: What does Flow already establish at dispatch and handback?

- Owner roles: solution-architect, business-analyst, product-manager
- Date: 2026-09-19
- Confidence: High for inspected repository behavior; medium for the proposed user outcome

## Question

Which existing Flow contracts should the first execution attempt reuse, and what evidence is absent?

## Method and sources

- `flow archive search 'execution provider receipt Shaper charter' --lane define --json` returned `no_matches`, selection `8bd330694ec9fd17626fbf927e365d3350e4a8e891d2b9a6ab29cb1bf53978e0`. This does not prove that no relevant decision exists.
- Role reviews: `research/architecture.md`, `research/workflow.md`, `research/product.md`, and `research/security.md`.
- Manually inspected outside that retrieval selection: `docs/adr/0001-separate-orchestration-contracts.md`, `scaffolds/default/standards/orchestration.md`, `cli/orchestration.py`, `cli/runstate.py`, `scaffolds/default/templates/agent-brief.md`, `.flow/PROJECT.md`.
- Proposal evidence: the two attached chat transcripts and the shared `Flow Shapping` chat. Their statements are proposals unless corroborated by current repository evidence.

## Findings

- ADR 0001 keeps `run.json` as a small lifecycle projection and places detailed, evolving orchestration data in the linked manifest. This applies directly to attempt and receipt detail; putting it in `run.json` would contradict the accepted decision.
- The manifest already declares assignment, provider identity, scopes, capabilities, output, coordination, and claim expectations. Dispatch validation checks these declarations.
- Handback validation checks output and reconciliation artifact existence, claim provenance shape, dispositions, and shared mutation evidence. It does not prove a worker ran, respected runtime grants, produced a particular commit, or told the semantic truth.
- The repository has no demonstrated general worker launcher or worktree execution contract in `cli/`. The user proposal identifies one Codex worker, one worktree, and a commit-bound receipt as the first learning slice.

## Implication for requirements

- Reuse the existing assignment and lifecycle identities and gates. Keep attempt detail outside `run.json` and preserve the existing validator's stated limits.
- Require a receipt that correlates one attempted invocation with its authorized inputs, provider, worktree baseline, outcome, validation, and resulting commit or explicit no-commit state.
- Keep the first slice to one worker and a bounded charter. Defer autonomous routing, retries, multi-agent topology, Shaper runtime, and MCP.

## Open follow-ups

- Engineer approval of the draft first-slice boundaries and exception authority.
- Solution lane: choose serialization, artifact linking, and exact provider launch mechanism without changing these logical requirements.
