# ADR 0002: Gate Semantic-Release Publication with Exact-Commit Candidate Evidence

- Status: accepted
- Date: 2026-09-01

## Context

The release workflow previously gave one job repository write permissions and
ran semantic-release before deterministic release checks. The v0.21.0 release
was safe only because a maintainer ran an equivalent gate manually before the
push. That protection was not encoded in the release path.

Semantic-release remains the authority for commit analysis, version selection,
and note rendering. Its dry-run mode still verifies push permission, and the
configured Git and GitHub plugins add side effects that a planning job must not
receive. Publication can also create a changelog release commit and tag before
a later GitHub release operation fails, so rollback is not reliably
transactional.

## Decision

Use four dependent jobs: `analyze`, `validate-candidate`, `publish`, and
`verify-published`.

Analysis runs semantic-release in preview mode against a writable local bare
remote, without a GitHub token. Preview and publication import one analyzer and
release-note policy; preview excludes changelog, Git, and GitHub plugins. The
Action's structured outputs become a strict, versioned release plan whose digest
binds the exact source SHA, previous release, predicted version and tag, and
release-note digest.

Candidate validation creates the predicted tag only in a local bare remote and
drives Flow's real install and update paths in isolated homes. A second
versioned artifact records every stable check and the plan digest. Publication
receives write permissions only after that evidence validates, refreshes the
remote branch and tag baseline, repeats preview, and rejects any disagreement
before invoking semantic-release once.

Post-publication verification is read-only. The generated release commit must
have the planned source as its single parent, change only `CHANGELOG.md`, carry
the expected subject, and be the target of the predicted tag. The GitHub release
and notes, public fresh installation, and public upgrade must also match the
plan.

There is no bypass, force push, automatic rollback, tag deletion, release
deletion, or blind retry. Pre-publication failures write nothing. Partial or
post-publication failures preserve actual state and repair forward with a
corrective commit.

If the publisher itself fails, a failure-only readback captures the plan,
candidate evidence, pre-publish baselines, and observed branch, tag, and GitHub
release state. Operators diagnose that artifact using the
[release failure runbook](../release-runbook.md); the readback never retries or
mutates publication.

## Consequences

- Release-producing runs take longer and a flaky blocker stops publication.
- Non-release commits remain cheap green no-ops.
- The plan and evidence artifacts provide an auditable identity chain across
  jobs without treating job outputs or console prose as trusted evidence.
- The one write-capable job retains the permissions required by the configured
  changelog, Git, and GitHub plugins; all earlier and later jobs are read-only.
- The transition release still needs the manual pre-push gate because the old
  workflow cannot validate its replacement retroactively.
- Live client discovery, applied routing, external identity, and actual
  capability grants remain manual because static runners cannot establish
  them.

## Rejected Alternatives

- Giving the analysis job a live write token solely to satisfy dry-run's push
  check would violate the credential boundary.
- Parsing semantic-release console output would make a human format part of the
  release contract.
- Reimplementing semantic-release version or note logic would create two
  release policies that can drift.
- Publishing first and validating afterward would continue to detect bad
  releases only after they became public.
- Deleting or rewriting a partially published release would turn a visible
  failure into destructive, history-changing recovery.
