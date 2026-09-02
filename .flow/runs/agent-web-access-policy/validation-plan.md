# Validation Plan: Global Flow Agent Web Access Policy

## Unit proof

- Default-enabled resolution for every final inventory name.
- Framework deny, user deny, omission preserving deny, and rationale-backed
  re-enable.
- Strict rejection of unknown names, invalid authorization, non-booleans,
  duplicate keys, missing/blank rationale, redundant enable, and capability
  fields embedded in agent records.
- Stable error fields include layer/path, agent, capability, rule, and fix.

## Renderer proof

- Parse Claude frontmatter and assert exactly one `WebSearch`/`WebFetch` when
  enabled, neither when disabled, and preservation of unrelated tools.
- Parse Codex TOML and assert the exact live/true or disabled/false pair.
- Assert one enabled or disabled guidance marker and repeat-render stability.
- Reject enabled or disabled Claude input without a `tools` key; accept an
  explicit empty list.

## Fake-home integration proof

- Traverse the complete post-merge agent inventory for both targets.
- Assert generated agent filenames match inventory and every decision maps
  correctly in both runtimes.
- Cover framework opt-out, same-name overlay body replacement without an
  exception, and user rationale-backed re-enable.
- Sync twice and compare all managed agent bytes.
- For malformed TOML and every invalid policy family, seed an existing agent
  output plus stale managed file and prove rejection leaves both byte-identical.

## Regression and mutation proof

- Focused capability and sync tests.
- Break one precedence or normalization rule temporarily and confirm its named
  test fails, then restore the implementation.
- `/opt/homebrew/bin/python3.12 -m unittest discover -s tests -p 'test_*.py'`
- `git diff --check`
- Isolated fake-home `flow sync claude --user`, `flow sync codex --user`, and
  both `--check` forms.
- `flow doctor --check` and `flow runtime smoke --target all --json`; retain
  live client/agent checks as `manual_required` rather than passing them.

## Review proof

- Security review: authorization, untrusted content, disclosure, denial
  persistence, shell-bypass wording, and fatal malformed overlay behavior.
- Architecture review: capability domain isolation, exception precedence,
  legacy mode, and coupled Codex mapping.
- Quality review: every acceptance criterion has reproducible evidence and no
  claim crosses the configuration-only boundary.

## Release proof

- Conventional `feat(agents): add semantic web research capability policy`
  source commit predicts v0.23.0.
- Push the reviewed source commit to `main`; the Release workflow must complete
  analyze, validate-candidate, publish, and verify-published.
- Candidate evidence must include full tests, staged install, fresh setup,
  prior-version upgrade, both sync checks, doctor, static runtime smoke, and
  representative CLI checks.
- Public evidence must identify the source SHA, generated release commit, tag,
  nonempty release notes, public fresh install, and public upgrade result.
- Archive only after hosted verification succeeds.

## Approved nonclaims

Passing evidence supports only: **web capability configuration passed**. It
does not prove live provider access, account entitlement, per-task enforcement,
disclosure prevention, instruction compliance, or delegated web invocation.
