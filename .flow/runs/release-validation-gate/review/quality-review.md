# Quality Acceptance Review

## Review Summary

**Verdict:** REQUEST CHANGES (interim)

**Overview:** Commit `298cca2` resolves the prior authentication blocker and
adds the requested failure, mutation, remote-baseline, and recovery coverage.
The implementation is materially ready, with 49 focused tests and 767 full-suite
tests passing on the current SHA. Final acceptance is still blocked locally by
stale candidate evidence, one uncovered prior-tag drift case, and full-branch
diff hygiene; public release evidence is necessarily pending until publication.

## Criterion-by-Criterion Verdict

| # | Verdict | Evidence and remaining gap |
|---|---|---|
| 1 | PASS by current contract | `.github/workflows/release.yml:117-181` requires candidate success before publication. All eight workflow mutations are detected by `tests/test_release_workflow.py:88-105`. A fresh candidate artifact for current SHA `298cca2` is still required. |
| 2 | PASS by current contract | Analysis still checks out `github.sha`, disables persisted credentials, uses only a local preview remote, and emits a versioned plan (`.github/workflows/release.yml:25-100`). Current retained plan evidence targets older SHA `7776703`, so it is historical rather than authorization for this commit. |
| 3 | PASS | No-release conditions remain explicit and the no-release-to-publication mutation is detected. |
| 4 | PASS in code; evidence refresh required | `scripts/release_candidate.py:283-297` retains all thirteen required checks. The older evidence proves those checks at `7776703`; the current full suite passes at `298cca2`, but a complete current-SHA candidate run has not yet replaced the retained evidence. |
| 5 | PASS in code; evidence refresh required | Candidate/previous local remotes and exact tag/SHA bindings are unchanged. Current retained install/upgrade proof is for `7776703`, not `298cca2`. |
| 6 | PASS by mutation/integration contract | `tests/test_release_workflow.py:256-310` induces each of the thirteen runner failures and proves later checks do not run. `tests/test_release_gate.py:232-257` proves every failed evidence position leaves the fake publication boundary and modeled external state unchanged. The runner itself writes candidate tags only to temporary local repositories. |
| 7 | PARTIAL | Moved-main and existing-candidate-tag cases now use real temporary remotes (`tests/test_release_recovery.py:52-95`), and repeated analysis/digest guards remain tested. A changed prior release tag/commit is still not covered, despite being an explicit acceptance case. |
| 8 | PASS by local contract; public proof pending | Generated release commit shape remains strict and unit tested. Actual `v0.22.0` tag ancestry can only be accepted after publication. |
| 9 | PASS in implementation; public proof pending | `scripts/release_verify_published.py:37-59` now reads the public GitHub API through credential-free `urllib`, removing the clean-runner `gh auth` failure. This review successfully read public release `v0.21.0` through that exact function. Fixture coverage rejects empty notes. Full `v0.22.0` tag, release, install, and upgrade proof awaits publication. |
| 10 | PASS by local contract; public proof pending | Publisher failure now triggers read-only reconciliation and artifact upload (`.github/workflows/release.yml:309-330`). `scripts/release_reconcile.py` and `tests/test_release_recovery.py:98-140` distinguish no observed write, partial publication, and incomplete inspection. The new runbook requires preservation and repair forward. |
| 11 | PASS statically | Workflow permissions still default to read-only and only `publish` receives write permissions. Every external action is now pinned to a full commit SHA. |
| 12 | PARTIAL | Ordering, conditions, permission isolation, contracts, all thirteen runner failures, all eight required workflow mutations, and recovery classifications are automated. The prior-tag drift case and an end-to-end local Git test of the complete published verifier remain absent. |
| 13 | PASS | The README, ADR, CLI guide, architecture guide, and new symptom-first `docs/release-runbook.md` distinguish candidate blockers, possible partial publication, published verification failures, manual checks, and repair-forward handling. |
| 14 | PASS locally | Analyzer, version rules, release-note rendering, branch, tag format, and pinned semantic-release/plugin versions remain shared and behaviorally unchanged. Hosted preview/publication parity remains pending. |

## Critical Issues

- None. The prior clean-runner authentication failure is resolved.

## Important Issues

- [`.flow/runs/release-validation-gate/release/candidate-plan.json:1`] The retained
  plan and candidate evidence authorize SHA `7776703`, while the reviewed branch
  is now `298cca2`. Rerun the real credential-free preview and all thirteen
  candidate checks at the final current SHA, replace the plan/evidence/logs, and
  validate their digests before publication. The current 767-test run proves the
  repository suite, but it is not a substitute for the install, upgrade, setup,
  sync, doctor, and runtime candidate chain.

- [`tests/test_release_recovery.py:52`] Remote-baseline integration now covers
  exact state, moved `main`, and an existing predicted tag, but not the explicit
  changed-prior-release identity failure. Add a case that moves or replaces
  `v0.21.0` (including the peeled commit identity) and prove
  `verify_remote_baseline` rejects it. This closes the remaining unsupported
  portion of acceptance criteria 7 and 12.

- [`.flow/runs/release-validation-gate/acceptance-criteria.md:17`] The remediation
  delta itself passes `git diff --check 7776703..HEAD`, but the required full
  branch check `git diff --check origin/main...HEAD` still fails on extra EOF
  blank lines across previously committed run artifacts. Remove those blank lines
  and rerun the full-branch check before handback.

- [`.flow/runs/release-validation-gate/validation-results.md:3`] The durable
  validation summary is stale: it still reports 37 focused tests, 754 full tests,
  pending mutation proof, and pending reviews. The retained older candidate log
  actually reports 755 tests, while the reviewer has now run 49 focused and 767
  full tests at `298cca2`. Refresh this file and `implementation-evidence.md` from
  the final current-SHA candidate run so the handback does not contradict its
  evidence.

## Suggestions

- [`tests/test_release_recovery.py:143`] Add one complete local-Git fixture for
  `release_verify_published.verify`, not only `_release_body`. It should build an
  actual changelog-only release commit/tag, use a release JSON fixture, stub only
  consumer commands, and assert both the passing result and a persisted
  repair-forward failure result. The public run will provide final proof, but
  this would catch orchestration mistakes before publication.

- [`scripts/release_gate.py:276`] Evidence log paths are textually constrained,
  but the validator does not resolve paths and reject a symlink escaping
  `logs_root`. Artifact producers are trusted within the workflow, so this is not
  a release blocker here; a resolved-path containment check would make the
  artifact boundary fully strict.

## What's Done Well

- Credential-free public lookup is now simple, read-only, and independently
  proven against an existing release.
- All thirteen candidate failure positions and all eight named workflow safety
  mutations are executable tests rather than prose claims; they passed during
  this review.
- Failure-only remote reconciliation captures branch, tag, and GitHub release
  observations without retrying or mutating state, and the runbook gives operators
  a concrete repair-forward path.
- Candidate evidence validation now requires `runner_sha == source_sha` and
  recomputes every uploaded log digest in both validation and publication jobs.
- External actions are pinned immutably while retaining readable version comments.
- Commit `298cca2 fix(release): close validation review gaps` follows Conventional
  Commits and keeps the remediation cohesive.

## Verification Story

- Tests reviewed: yes. `python3 -m unittest tests.test_release_gate
  tests.test_release_workflow tests.test_release_recovery` passed 49 tests.
  `python3 -m unittest discover -s tests -p 'test_*.py'` passed 767 tests at
  current SHA `298cca2` in 159.472 seconds.
- Build/runtime checks reviewed: partially current. The prior thirteen-check
  candidate bundle is internally consistent but belongs to SHA `7776703`; it
  must be regenerated for `298cca2`.
- Mutation check: ran. All eight required workflow mutations were detected, and
  every one of the thirteen injected candidate failures stopped later checks.
- Public read check: ran against existing `v0.21.0`; credential-free lookup
  returned the expected release URL and a non-empty 565-character body.
- Diff hygiene: remediation delta passes; full `origin/main...HEAD` diff fails on
  documented EOF blank lines in earlier run artifacts.
- Validated against: current source for focused/full automated tests; older exact
  source for the retained candidate installation chain; existing public `v0.21.0`
  for credential-free API lookup. No `v0.22.0` publication or public consumer
  evidence exists yet.
- Remaining risks: current-SHA candidate proof, prior-tag drift coverage, durable
  evidence refresh, and full-branch diff hygiene remain before publication. After
  publication, verify tag/release-commit shape, release notes, public fresh install,
  public upgrade, setup, sync, doctor, and runtime smoke before final acceptance.
  Data migration and UX review do not apply to this workflow/tooling change.
