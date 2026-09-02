# Handoff: Agent Web Access Policy

## Status

Implementation is locally validated and approved for release. The first hosted
candidate stopped before publication on a disposable Git-fixture race. The
fixture is stabilized and a corrective release attempt is next; hosted release
evidence and archive remain.

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

## Remaining actions

1. Commit the release-fixture stabilization and push to `main`.
2. Verify the fresh release workflow predicts and publishes v0.23.0.
3. Verify public tag, release notes, fresh install, and prior-version upgrade.
4. Update this handoff and validation evidence with final release identifiers.
5. Archive the run and publish the closeout state.

## Release recovery

- Attempt 1: GitHub Actions run `33670068165`.
- Result: candidate validation failed; publication and verification were
  skipped; no public release state changed.
- Recovery: Git auto-maintenance is disabled only inside disposable test
  repositories, and both focused stress and complete local validation pass.

## Residual risk

Passing evidence proves generated configuration only. Live provider access,
runtime enforcement, task-level compliance, and disclosure prevention remain
unverified by explicit approved design.
