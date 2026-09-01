# Implementation Test Plan: Automated Release Validation Gate

## Test posture

The release gate is a shared-external-mutation control. Tests must prove the
absence of publication on a failed candidate path, not merely that the happy
path can publish. No unit or integration test needs a GitHub write token. The
test seam is a fake publisher plus local bare Git remotes; GitHub Actions YAML
is a separately tested contract.

The existing standard-library suite in `tests/test_flow.py` is the baseline.
It already proves release staging/import integrity, release and bootstrap
installs, release-mode update behavior, sync, `doctor`, runtime smoke, and
generated-help drift. Extend it with a focused release-gate test class and a
small fixture directory for normalized preview results and controlled git
histories. Keep one source of truth for stable check IDs in the gate helper.

## Fixture architecture

### Normalized analysis fixtures

Use checked-in JSON fixtures, never semantic-release console output:

- `release-required.json`: valid `feat` result with source SHA, prior tag and
  commit, version/tag/type, notes, rendered-entry count, and tool-policy
  identity.
- `no-release.json`: valid `release_required: false` result with no predicted
  version/tag/notes.
- `breaking-pre-1.0.json`, `fix.json`, `docs.json`, and `mixed-history.json`:
  policy-parity cases. These prove the existing release rules and pinned note
  renderer are preserved rather than reimplemented.
- malformed, unsupported-schema, empty-notes, invalid-tag, invalid-SHA,
  unexpected-field-type, and unsafe-log-path fixtures.

Use deterministic 40-hex SHA fixtures and fixed clock/run identifiers. Tests
must assert canonical JSON bytes and SHA-256 digests, so a plan/evidence
comparison does not depend on key order, path separators, clock time, or
Action-output formatting.

### Local Git fixture

Create a helper modeled on `make_fake_remote_with_tags` in `tests/test_flow.py`
that creates:

1. a source repository with an explicit previous tagged commit;
2. a candidate source commit at a distinct SHA;
3. a bare remote with the previous tag and a local-only predicted candidate
   tag pointing at the candidate SHA; and
4. optional remote movement after plan creation (new `main` commit, retargeted
   prior tag, or pre-existing candidate tag) for stale-state tests.

It must expose the exact remote URL, previous tag/commit, candidate tag/commit,
and expected release version. The candidate remote must be local-only and never
point at GitHub. Every fake HOME is unique; no test may read or mutate a real
`~/.flow`, user runtime directory, tag, release, or changelog.

### Fake process and publisher boundary

Inject a command runner and publisher into the release-gate orchestration.
The fake runner returns fixture analysis results and records command argv,
environment names (not secret values), working directory, and mutations. The
fake publisher records attempted `publish` calls, tag/release/changelog writes,
and receives a single controlled result. It must be impossible for tests to
accidentally fall through to semantic-release or GitHub.

The standard assertion for every pre-publication failure is:

```text
result = failed
fake_publisher.calls == []
remote tags unchanged
remote release state unchanged
working-tree changelog bytes unchanged
```

## Stable deterministic candidate checks

The runner should emit these identifiers in this order. They are an API between
the runner, evidence validator, workflow, logs, and tests; do not derive them
from display strings.

| ID | Proof target | Existing surface or test shape |
| --- | --- | --- |
| `python-test-suite` | Full behavior suite passes | `python -m pytest` / existing `tests/test_flow.py` |
| `generated-help` | Generated help equals manifest | `scripts/regenerate-flow-help.py --check` |
| `release-staging` | Candidate CLI parses and transitive imports resolve | existing lifecycle staging tests plus candidate tree |
| `clean-tracked-tree` | Generated checks did not leave tracked changes | `git diff --check` and tracked-tree status helper |
| `candidate-fresh-install` | Bootstrap path selects/installs predicted candidate tag | local bare remote + temporary HOME |
| `candidate-upgrade` | Previous release updates atomically to candidate | prior-tag install + `flow update` against local remote |
| `setup-machine` | Candidate creates machine state | temporary HOME |
| `setup-user` | Candidate creates user runtime surfaces | temporary HOME |
| `claude-sync-check` | Generated Claude surfaces are clean | `flow sync claude --user --check` |
| `codex-sync-check` | Generated Codex surfaces are clean | `flow sync codex --user --check` |
| `doctor-check` | Installed candidate reports no actionable drift | `flow doctor --check` |
| `runtime-smoke-static` | Static Claude/Codex surface contract holds | `flow runtime smoke --target all` |
| `representative-cli` | Changed release-gate CLI behavior is callable | exact new helper/CLI command, with JSON contract assertion |

The evidence schema must require every ID exactly once, reject unknown IDs and
duplicates, preserve order, and include outcome, exit code, duration, log
path/hash, runner SHA, candidate version/tag, and plan digest. A passing
overall result cannot be constructed with a missing check.

## Contract and unit matrix

| Area | Test cases | Critical assertions |
| --- | --- | --- |
| Plan normalization | valid release, valid no-release, malformed output, schema/version/type errors | release result has validated SHA/version/tag/notes digest; no-release has no prediction; values are never accepted by shell before validation |
| Plan digest | canonical bytes, reordered object keys, changed SHA/tag/version/type/notes/prior tag | same semantic document has stable digest; every protected-field change rejects |
| Evidence | complete pass, each stable ID failing, duplicate/unknown/missing ID, bad log hash/path | complete evidence only; failure is retained and blocks; unsafe paths rejected |
| Identity comparison | plan vs candidate evidence vs repeated preview | source SHA, prior tag+commit, predicted type/version/tag, notes digest, policy identity, and plan digest must agree exactly |
| No-release | valid no-release plan, malformed no-release plan | successful no-op skips candidate/publisher/public verifier; malformed result does not silently become a no-op |
| Notes safety | metacharacters, newlines, quotes, command substitutions, and oversized input | treated as data; hash and entry count are correct; no command construction evaluates contents |
| Publish preparation | stale main, changed previous tag, candidate tag already moved, plan/evidence mismatch, preview disagreement | publication refuses before publisher call and names the identity difference |
| Generated release commit | allowed changelog-only generated commit vs unrelated file/change/incorrect ancestry | verifier accepts only the documented semantic-release generated commit relationship |
| Repair-forward classification | pre-publish failure, publish boundary failure, post-publish verifier failure | pre-publish = prevented publication; post-publish = published and repair-forward; no delete/rewrite action is offered |

## Workflow-contract tests

Test workflow structure without running Actions. A focused test may read the
YAML text plus a deliberately narrow parser, or use a tiny checked-in fixture
representation if the implementation avoids adding a YAML dependency. Assert
meaningful relations rather than brittle line numbers:

1. Jobs are exactly `analyze → validate-candidate → publish → verify-published`.
2. Root permissions are read-only. `publish` alone has only the write scopes
   required by the configured semantic-release plugins; `analyze`, candidate,
   and public verification have no write token or persisted checkout
   credential.
3. All checkouts use the planned SHA or the event SHA in analysis, never a
   moving `main` ref. Full history/tag fetch behavior remains present.
4. Candidate requires a valid release-required plan; publish requires a
   passing evidence result and matching plan digest; public verification
   requires successful publication. No-release conditions skip all three
   downstream jobs.
5. Concurrency remains one serialized release group with cancellation disabled.
6. No `workflow_dispatch` bypass, input-controlled bypass, `continue-on-error`,
   `always()` rescue condition, force push, tag deletion, or failure-tolerant
   publish condition exists.
7. The preview/publish policy invokes the same configuration identity and the
   workflow uploads/downloads only the validated plan/evidence artifacts.

Mutation checks must alter one required relation at a time and name the test
that fails: remove publish's candidate dependency; pass a token to analysis;
replace a pinned checkout with `main`; remove digest comparison; add
`continue-on-error` to one candidate check; call publish on the no-release
path; or label a public-verification failure as prevented publication.

## Integration matrix: candidate and no-write proof

### Candidate fresh install

From the local bare remote, run the bootstrap installer with `FLOW_REPO_URL`
set to that remote. Assert:

- selected tag is the predicted candidate tag;
- installed config is release mode and exactly that version;
- installed source identity/content is the candidate, not the runner checkout;
- `flow setup machine`, `flow setup user`, both sync checks, `doctor --check`,
  static runtime smoke, and `representative-cli` pass in the temporary HOME.

Induce invalid candidate staging or install failure. Assert no candidate evidence
success and no publisher call; where the installation has started, assert the
old source/config remains usable and unchanged according to the lifecycle
atomic-swap contract.

### Candidate update

Bootstrap-install the previous tag from the same local remote. Run update to
the candidate tag, then assert exact candidate config version, source identity,
and all setup/sync/doctor/smoke/representative behavior. Induce a bad staged
candidate (missing transitive CLI module or validation failure) and assert the
previous release remains runnable with its original config/version. This is the
existing release-staging/update behavior exercised through the gate, not a
mocked substitute.

### Failure/no-write parameterization

Parameterize one orchestration test over all stable IDs. For each ID, inject a
nonzero result at that check and assert failed evidence naming that ID, no later
check execution, no publisher invocation, and unchanged local remote/tag,
fake GitHub release inventory, and working-tree `CHANGELOG.md` bytes. Separate
tests cover analysis malformed/empty/no-release cases and all pre-publish
identity mismatches. This gives a reproducible proof that every declared
candidate blocker actually blocks writing.

## Policy-parity and divergence tests

Use the representative history fixtures to invoke the shared preview and
publication analysis adapter in nonpublishing mode. For `feat`, `fix`, docs,
maintenance/no-release, breaking pre-1.0, and mixed history, assert identical
prior tag, release type, version, tag, rendered notes, notes digest, and policy
identity. Then mutate one result field at a time and prove the publish guard
rejects it. This catches dry-run/publish divergence without publishing.

Also cover a superseded source: create the plan for commit A, advance remote
`main` to B, and require publication of A to stop before write. Cover a changed
prior tag separately; it is not sufficient merely to compare version strings.

## Post-publication verifier tests

The verifier is deliberately not a pre-publication gate. Test it against local
Git fixtures and a fake read-only release API:

- tag/version/notes/changelog/release values match the recorded plan;
- tag points to a valid generated release commit shape, whose parent/ancestry
  contains the validated source and whose allowed diff is only configured
  generated release content;
- public bootstrap install selects the tag; previous public release updates to
  it; then setup, sync checks, doctor, smoke, and representative behavior pass;
- absent tag/release, empty/mismatched notes, unexpected diff, ancestry error,
  public-install failure, and update failure all produce a red repair-forward
  result that records actual state and does not call a deletion, retagging, or
  rollback boundary.

Live Claude/Codex command discovery and applied model/effort routing remain
manual checks. Tests must assert the documentation/evidence labels them
`manual` or `unverified`, never `passed`.

## Local pre-publication execution

Before a release push, run:

1. focused release-gate contract/workflow tests;
2. `python -m pytest`;
3. `python scripts/regenerate-flow-help.py --check`;
4. release-staging/import validation and `git diff --check`;
5. local candidate fresh-install and upgrade integrations;
6. candidate setup, both sync checks, `doctor --check`, static runtime smoke,
   and representative CLI invocation; and
7. the mutation suite above, restoring each mutation before the next run.

For the transition release, execute the same manual gate because the old
workflow cannot validate the workflow change retroactively. After publication,
run the post-publication verifier and attach source SHA, predicted/published
version, tag target, release commit, plan/evidence digests, logs, and the
workflow URL to the run handback.

## Acceptance mapping

- Criteria 1, 6, 7, and 12: fake-publisher failure/no-write, identity, and
  workflow-mutation tests.
- Criteria 2, 3, 5, 11: plan contracts, no-release, local remote, and
  permission/checkout contract tests.
- Criteria 4 and 14: stable-ID candidate runner plus parity fixtures against
  the existing test/install/staging surfaces.
- Criteria 8–10: generated-release ancestry and post-publication verifier
  fixtures, including repair-forward failures.
- Criteria 13: documentation assertion that separates blocking, post-publish,
  and manual client checks.
