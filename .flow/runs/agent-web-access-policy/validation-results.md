# Validation Results: Agent Web Access Policy

- Status: released and public verification passed.
- Approved claim: **web capability configuration passed**.

## Automated tests

- `/opt/homebrew/bin/python3.12 -m unittest discover -s tests -p 'test_*.py'`
  — 789 tests passed in 179.129 seconds.
- After the hosted Linux fixture failure, the two affected update tests passed
  ten consecutive focused runs and the full 789-test suite passed again in
  186.882 seconds.
- Focused resolver and adapter tests passed after the final fail-closed fix.
- `git diff --check` passed.

## Hosted release attempt 1

- GitHub Actions run `33670068165` analyzed source commit
  `95968e9cea6061d3d9004b1bfcab675470536284` and predicted v0.23.0.
- Candidate validation stopped at `python-test-suite`; publish and verify were
  skipped, so no tag or GitHub release was created.
- The two errors were filesystem races in disposable Git repositories: a
  detached auto-maintenance writer overlapped temporary-directory teardown and
  a following bare clone lost an object directory during copy.
- Corrective action: disable Git auto-GC and maintenance for the disposable
  fixture commands. This changes test isolation only, not product behavior.

## Hosted release attempt 2

- GitHub Actions run `33670991492` analyzed source commit
  `b4153ba63170b27fa4ac8f70aefd6d09572bd360` and published v0.23.0.
- Analyze, candidate validation, publication, and published verification all
  passed.
- Candidate evidence reported every deterministic check passed, including the
  Python suite, fresh install, prior-version upgrade, setup, Claude and Codex
  sync checks, doctor, static runtime smoke, and representative CLI checks.
- Published verification independently passed the public tag and generated
  commit, nonempty GitHub release notes, public fresh install, public upgrade,
  setup, both sync adapters, doctor, static smoke, and representative CLI.
- Generated release commit:
  `00a23c13cf2c57b66f7d1205f1d030b134bf6547`.
- Public release: https://github.com/andyconley/flow/releases/tag/v0.23.0

## Mutation check

- Ran: removed `WebFetch` from the enabled Claude renderer.
- Detection: `test_web_capability_default_renders_for_complete_agent_inventory`
  failed for all thirteen agents because `WebFetch` count was zero.
- Restore: restored the exact enabled pair; the named test and final full suite
  passed.

## Isolated runtime configuration

- Installed the working tree in develop mode under an isolated temporary home.
- `flow setup machine` and `flow setup user` passed.
- `flow sync claude --user --check` passed.
- `flow sync codex --user --check` passed.
- `flow doctor --check --json` reported `ok: true`, zero errors, and only the
  expected runtime/manual and empty-isolated-telemetry warnings.
- `flow runtime smoke --target all --json` reported `ok: true`, zero static
  failures, and four `manual_required` client checks.

## Review

- Security: approved for release, zero open findings after re-review.
- Architecture/acceptance: approved, zero open findings after the disabled
  Claude missing-tools correction.

## Nonclaims

No live web request, provider entitlement, per-task technical enforcement,
disclosure-prevention exercise, instruction-compliance test, or delegated web
invocation was performed or claimed.
