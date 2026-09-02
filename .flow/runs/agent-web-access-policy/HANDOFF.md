# Handoff: Agent Web Access Policy

## Status

Released as v0.23.0. The exact candidate and public release passed all hosted
gates. Archive closeout is in progress.

## Delivered

- Reusable semantic `web_research` default and keyed exception ledger.
- Overlay-safe opt-out and rationale-backed re-enable behavior.
- Fail-closed malformed overlay and explicit Claude tool-list validation.
- Claude exact-once `WebSearch`/`WebFetch` mapping.
- Codex coupled live/true and disabled/false mapping.
- Shared task-authorization, untrusted-content, disclosure, citation, and
  local-truth guidance.
- Full inventory, negative, idempotence, atomicity, and legacy tests.
- ADR, runtime mapping, migration, and rollback documentation.

## Proof

- 789-test full suite passed.
- The two affected tests passed ten consecutive corrective stress runs, then
  the full 789-test suite passed again in 186.882 seconds.
- Mutation check proved the inventory test detects a missing native tool.
- Isolated setup, both sync checks, doctor, and static runtime smoke passed.
- Security and architecture/acceptance review have zero open findings.
- GitHub Actions run `33670991492` passed analyze, candidate validation,
  publication, and published verification.
- Public tag and release notes, fresh install, prior-version upgrade, setup,
  Claude and Codex sync checks, doctor, static smoke, and representative CLI
  checks passed.

## Remaining actions

1. Archive the accepted run.
2. Publish the archive-only closeout commit without starting another release.

## Release recovery

- Attempt 1: GitHub Actions run `33670068165`.
- Result: candidate validation failed; publication and verification were
  skipped; no public release state changed.
- Recovery: Git auto-maintenance is disabled only inside disposable test
  repositories, and both focused stress and complete local validation pass.
- Attempt 2: GitHub Actions run `33670991492` passed.
- Source commit: `b4153ba63170b27fa4ac8f70aefd6d09572bd360`.
- Release commit: `00a23c13cf2c57b66f7d1205f1d030b134bf6547`.
- Public release: https://github.com/andyconley/flow/releases/tag/v0.23.0

## Residual risk

Passing evidence proves generated configuration only. Live provider access,
runtime enforcement, task-level compliance, and disclosure prevention remain
unverified by explicit approved design.
