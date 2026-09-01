# Test Validation: Release Validation Gate

## Verdict

**PASS for pre-publication implementation validation.** The release gate's
deterministic contracts, failure matrix, workflow mutation checks, and recovery
path pass at reviewed commit `ebdaf02bb62d99eff7f83edd6e7745f33be532df`.

This is not publication evidence. The retained candidate plan and evidence are
bound to `777670320a65ec713947bea7ca043d3321b5cee0`; they are useful historical
evidence only and cannot authorize the reviewed commit. Regenerate the preview,
candidate evidence, and logs for the final immutable pre-push SHA, then let the
hosted workflow produce the public-release proof.

## Test Coverage Analysis

### Current Coverage

- `python3 -m unittest tests.test_release_workflow tests.test_release_gate -v`
  passed: **44 tests**.
- `git diff --check` passed.
- The workflow contract test finds no current violations: ordering and job
  dependencies, exact-SHA checkout, read-only defaults, publish-only write
  token, no-release conditions, no bypass/force/delete path, artifact digest
  binding, immutable action references, safe note transport, and repair-forward
  wording.
- `test_every_injected_runner_failure_stops_later_checks` injects a failure at
  every one of the thirteen stable candidate checks and proves that later checks
  are recorded as `not_run`. `test_each_failed_check_blocks_fake_publisher`
  independently proves every failed evidence check prevents the fake publisher.
- `test_required_source_mutations_are_detected` applies each required workflow
  mutant to an in-memory copy of the checked-in workflow and asserts its named
  detector fires: missing candidate dependency, analysis credential, moving
  checkout, missing evidence digest, failure bypass, no-release publication,
  incorrect public-failure classification, and shell interpolation of notes.
  The checked-in workflow then has zero findings. This is source-text mutation
  coverage; it intentionally leaves the working file unchanged.
- Release-plan/evidence tests reject identity, digest, ordering, log, runner,
  and publication-shape drift. The latest containment test also rejects a log
  symlink escaping the uploaded evidence root.
- Recovery tests cover moved main, existing candidate tag, clean/partial/
  incomplete publisher-failure reconciliation, and GitHub release fixtures with
  empty-notes rejection.

### Coverage Gaps

- No public release has occurred yet, so tag ancestry, generated changelog,
  GitHub release notes, public fresh install, public upgrade, and hosted job
  ordering remain public-only proof.
- The candidate run retained in this work directory passed all thirteen checks,
  but its source SHA is stale (`7776703` rather than `ebdaf02`). A new final-SHA
  run is mandatory.
- The full repository suite was previously exercised by the candidate run, but
  this review reran the proportionate focused release suite. The final candidate
  gate must repeat the full suite at the final SHA.
- The workflow receives real Actions integration only after the transition push;
  local tests deliberately use fake/local boundaries and do not publish.

## Required Pre-Push and Public Proof

1. Freeze the intended source commit, refresh remote/tag baseline, and generate
   a semantic-release preview for that exact SHA.
2. Run `scripts/release_candidate.py` for that plan. It must pass all thirteen
   checks and produce matching evidence/log digests.
3. Confirm the branch and tag baseline immediately before push. Do not reuse the
   stale `7776703` evidence.
4. After the transition push, retain the hosted workflow URL and artifacts;
   verify the tag/release/changelog/notes and public fresh-install and upgrade
   results. Any failed public verifier is a red repair-forward event, not a
   prevented publication.

## Verification Notes

- Manual checks: use `docs/release-runbook.md` if the hosted candidate,
  publisher, or public verification phase fails; preserve artifacts and remote
  state before a corrective commit.
- Runtime checks: hosted Actions is the remaining integration boundary. The
  publisher must execute exactly once only after candidate success.
