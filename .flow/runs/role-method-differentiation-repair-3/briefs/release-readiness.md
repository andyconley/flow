# Release-readiness brief

## Objective

Assess the validated candidate's operational readiness for the repository's
semantic-release pipeline, develop-install refresh, and Claude/Codex readback.

## Evidence inventory

- approved repair-3 plan and validation plan
- `.github/workflows/release.yml`, `release.config.cjs`, and
  `docs/release-runbook.md`
- candidate validation, doctor, sync, smoke, and native-client records

## Boundaries

Write only `research/release-readiness.md`. Do not publish, push, tag, or edit
production files. Other agents are working in the repository; do not revert or
rewrite their work.

## Output

State release blockers, rollback/repair-forward conditions, and the checks that
must be repeated after `R` is published.
