# Validation Results: Agent Web Access Policy

- Status: local implementation validation passed; release validation pending.
- Approved claim: **web capability configuration passed**.

## Automated tests

- `/opt/homebrew/bin/python3.12 -m unittest discover -s tests -p 'test_*.py'`
  — 789 tests passed in 179.129 seconds.
- Focused resolver and adapter tests passed after the final fail-closed fix.
- `git diff --check` passed.

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
