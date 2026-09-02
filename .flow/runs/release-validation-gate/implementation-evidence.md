# Implementation Evidence

## Shipped change

- The release workflow is a four-stage
  `analyze -> validate-candidate -> publish -> verify-published` gate.
- Release intent, candidate evidence, publication result, and public verification
  use versioned structured contracts bound to the exact source SHA and digests.
- Only the serialized publish job receives repository write permission and a
  live token. Preview, validation, and public verification are read-only.
- Candidate validation runs thirteen deterministic checks in an isolated home,
  including the full suite, fresh install, upgrade, setup, sync, doctor, static
  runtime smoke, and a representative CLI path.
- Remote drift, log containment and hashes, generated commit shape, release
  notes, and public consumer behavior are fail-closed contracts.
- Failure reconciliation is read-only and the runbook requires repair forward;
  it never deletes tags, releases, or history.

## Implementation commits

- `e61c74d chore(flow): record release validation gate run`
- `f8fd9d5 feat(release): add validated release planning contracts`
- `83918bc feat(release): validate candidate and published artifacts`
- `0393e46 ci(release): gate publication on candidate evidence`
- `cf00921 docs(release): document release gate operations`
- `02a8254 fix(release): stabilize preview note links`
- `96eeb76 fix(release): seed candidate overlay for doctor`
- `7776703 fix(release): classify isolated doctor warnings`
- `298cca2 fix(release): close validation review gaps`
- `ebdaf02 fix(release): contain uploaded validation logs`
- `8719b8b test(release): cover prior tag drift`
- `5b62eca chore(flow): record release gate reviews`
- `cad5129 fix(release): preserve canonical preview URL`
- `e05178b fix(release): isolate candidate test environment`
- `f5f4556 chore(release): 0.22.0 [skip ci]` (generated publication commit)

## Exact candidate proof

Hosted run `33632240778` validated source
`e05178b78420db53c3f7431448e1d188cc958441`:

- 13 of 13 candidate checks passed.
- The full suite passed 770 tests.
- The focused contract, integration, and recovery suites passed 52 tests.
- The plan digest was
  `b503b30400e1d56dec75fc850bea71dd4456eec3496ad76d8e9a12c0a1823e7d`.
- The candidate evidence digest was
  `f762fbccbc20ba8a9a01a80d88b0bfe7b51f1de2e9d9dc1e2d38911b129f2166`.

Retained hosted plans, evidence, logs, baseline, publication result, and public
verification are under `release/hosted/`.

## Failure and mutation proof

- Thirteen injected candidate failures each stopped later checks and left the
  modeled publication boundary unchanged.
- Eight workflow mutations were rejected by named contract findings.
- A real mutation removing the publish dependency caused the corresponding
  contract test to fail; restoring the dependency restored the pass.
- Hosted run `33564014091` failed during read-only analysis; no publication
  steps ran and the remote was unchanged.
- Hosted run `33565098215` failed during candidate validation; publish and
  public verification were skipped and the remote was unchanged.

## Publication and public proof

Hosted run `33632240778` passed all four jobs and published `v0.22.0`:

- GitHub release: `https://github.com/andyconley/flow/releases/tag/v0.22.0`
- generated release commit: `f5f45565c64f881f9ba07c85d23fb95e90cb292b`
- generated commit parent: exact validated source `e05178b`
- generated commit contents: `CHANGELOG.md` only
- public verifier: 11 of 11 checks passed, including fresh install and upgrade
- unexpected shared-state delta: none

## Remaining boundary

Live Claude/Codex client discovery and applied model/effort routing cannot be
proved by the non-interactive release runner. Static generated surfaces and
sync checks passed; interactive client behavior remains a manual smoke check.
