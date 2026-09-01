# Implementation Handoff: Automated Release Validation Gate

## Header

- Work item: `release-validation-gate`
- Work type: release automation, CI safety, test infrastructure, and documentation
- Branch: `codex/release-validation-gate`
- Source base: `origin/main` at `2f48aad`, after v0.21.0
- Canonical plan: `.flow/runs/release-validation-gate/plan.md`

## Problem statement

Flow can currently publish before its deterministic release evidence exists. v0.21.0 used a complete manual gate; this work makes the same proof an enforced part of every release-producing workflow run.

## Desired outcome

The exact source SHA is analyzed without live write credentials, validated as a local release candidate, published only after all deterministic checks pass, and then verified as a public artifact. Non-release commits remain cheap no-ops. Failures have no bypass and repair forward after publication.

## In scope

- Four-stage release workflow
- Shared semantic-release preview/publication policy
- Versioned release-plan and release-evidence contracts
- Candidate fresh-install and upgrade validation through a local repository
- Publication identity and permission guards
- Public-tag verification
- Workflow, helper, integration, and failure/no-write tests
- ADR and maintainer/release documentation
- Full release and released-artifact proof

## Out of scope

- Live client discovery or applied routing checks
- External identity and actual capability proof
- Versioning-policy changes
- General PR CI expansion
- Manual override, rollback, tag deletion, or history rewriting
- Canonical checkout `docs/backlog.md`

## Required implementation preparation

Before dispatch, update `orchestration.json` from the planning manifest to a high-risk shared-mutation manifest because the work changes a write-capable release workflow and will eventually publish to GitHub. It must include:

- implementation producer and evidence collector assignments
- a distinct read-only security/acceptance verifier
- confirmed capabilities for each assignment
- exact repository target and serialized publication ownership
- fresh remote/tag baseline before publication
- expected tag, release, changelog, and branch deltas
- recovery posture and repair-forward safeguards
- post-write readback and comparison evidence

Run dispatch validation before assigning implementation or enabling publication.

## Likely change surface

- `.github/workflows/release.yml`
- `release.config.cjs`
- new release-gate helpers under `scripts/`
- focused and integration tests under `tests/`
- release, architecture, and maintainer documentation
- ADR under `docs/adr/`

## Architectural rules

- Release policy has one source shared by preview and publication.
- No semantic-release console-log parsing.
- No GitHub write token before the publication job.
- Every stage binds to the exact SHA, version, prior tag, and artifact digest.
- Only publication may mutate remote release state.
- Public verification reports repair-forward failures honestly.
- Release notes and artifact content never become executable shell input.

## Acceptance criteria

Use `.flow/runs/release-validation-gate/acceptance-criteria.md` without weakening or summarizing it. Record any deviation and obtain approval before release.

## Required handback

- Files, workflow, contracts, and permissions changed
- Focused, full-suite, candidate, and mutation evidence
- Proof that each pre-publication failure prevents publisher invocation
- Security and quality review dispositions
- Exact SHA/version/tag/evidence relationships
- Workflow and GitHub release URLs
- Public fresh-install and upgrade results
- Manual live-client limitations
- Capability-gap disposition and remaining risks

