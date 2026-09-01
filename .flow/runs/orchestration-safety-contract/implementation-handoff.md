# Implementation Handoff: Orchestration Safety Contract

## Header

- Work item: `orchestration-safety-contract`
- Work type: framework behavior, CLI validation, runtime contracts, and release
- Branch: `codex/orchestration-safety`
- Source base: `origin/main` at `v0.20.2`
- Canonical plan: `.flow/runs/orchestration-safety-contract/plan.md`

## Problem statement

Flow has lifecycle and evidence primitives but does not enforce safe delegation, claim lineage, shared-state coordination, or verification independence at the handoff points. Repeated backlog observations show role briefs exceeding capabilities, unsupported claims entering durable artifacts, author-only evidence carrying full weight, and external mutations lacking reliable run records and recovery checks.

## Desired outcome

A revision-2 Flow run carries one machine-readable orchestration contract. The CLI validates it before dispatch, handback, and acceptance; existing runs remain compatible; readable standards and templates tell humans and agents how to produce the evidence; and the complete feature ships as a verified minor release.

## In scope

- Canonical orchestration standard and templates
- Claim classification and reconciliation
- Shared/external mutation safety
- Deterministic risk calculation and independent high-risk verification
- Standard-library validator and CLI command
- Lifecycle gate integration with protocol compatibility
- Command, framework, README, architecture, file-model, CLI, and runtime documentation
- Unit, integration, compatibility, generated-surface, installation, and release verification
- Commit, push, automated release, and released-artifact validation

## Out of scope

- New orchestration phase or command
- Agent-launching runtime
- SaaS-specific automation or credentials
- Semantic truth detection
- Recurring operations lane
- Retrofitting older runs
- Existing unrelated `docs/backlog.md` changes in the canonical checkout

## Technical constraints

- New CLI module: `cli/orchestration.py`
- Existing lifecycle integration: `cli/runstate.py` and `cli/flow.py`
- No third-party Python dependency
- `run.json` schema stays at version 1; additive `protocol_revision` selects enforcement
- Detailed state stays in `.flow/runs/<work-id>/orchestration.json`
- Generated runtime files are outputs, never the hand-edited source of truth
- Failure diagnostics must not print sensitive artifact contents

## Required implementation sequence

1. Contract, templates, and ADR
2. Validator and focused tests
3. Lifecycle integration and compatibility tests
4. Command/docs/runtime integration
5. Full review, release, and released-artifact proof

Do not begin lifecycle integration before validator behavior and error contracts are covered. Do not push until acceptance review is complete and the final remote/diff checks pass.

## Acceptance criteria

Use `.flow/runs/orchestration-safety-contract/acceptance-criteria.md` without weakening or summarizing it. Any deviation must be recorded in the handback and explicitly accepted before release.

## Required handback

- Files and contracts changed
- Test and compatibility evidence
- Generated Claude/Codex surface evidence
- Security and sensitive-evidence review
- Deviations from plan
- Remaining risks and limitations
- Commit and remote details
- Release tag, GitHub release, changelog, and notes verification
- Clean installation/update and runtime-smoke results from the released tag
