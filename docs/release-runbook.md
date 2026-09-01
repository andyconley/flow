# Release Failure Runbook

Use this runbook when the `Release` workflow is red. Preserve the remote state
and the workflow artifacts before taking corrective action. Do not rerun the
publisher blindly, force-push, delete a tag or release, or edit generated
release state by hand.

The Flow maintainer who pushed the release-impacting commit owns initial
diagnosis. Escalate to a repository administrator before changing branch
protection, workflow permissions, or any remote release state.

## Candidate validation failed

**Symptoms:** `validate-candidate` is red; `publish` and `verify-published` are
skipped; no `release-publication-*` artifact exists.

1. Download `release-plan-*` and `release-evidence-*` from the failed run.
2. Read `overall_result`, then find the first failed check in
   `release-evidence.json`. Open its matching file under `logs/`.
3. Confirm that the predicted tag does not exist and `main` did not gain a
   generated release commit:

   ```bash
   git ls-remote origin refs/heads/main refs/tags/vX.Y.Z
   ```

4. Fix the candidate failure in a normal Conventional Commit and push it. The
   next workflow run will analyze and validate the new exact SHA.

## Publish failed or may have written partial state

**Symptoms:** `publish` is red at `Publish once`; `verify-published` is skipped;
the `release-publication-failure-*` artifact contains
`partial-publication.json`.

1. Download the failure artifact before rerunning anything. It retains the
   plan, candidate evidence, two pre-publish baselines, and read-only remote
   reconciliation.
2. Inspect `classification`, `inspection_errors`, `observed.main_sha`,
   `observed.tag_sha`, and `observed.github_release`. Confirm independently:

   ```bash
   git ls-remote origin refs/heads/main refs/tags/vX.Y.Z 'refs/tags/vX.Y.Z^{}'
   curl -fsSL https://api.github.com/repos/andyconley/flow/releases/tags/vX.Y.Z
   ```

3. If no write is observed, diagnose the publisher failure and use a new
   corrective commit. Do not rerun the failed job because the remote may have
   changed after reconciliation.
4. If the branch, tag, or GitHub release exists, treat the release as partial.
   Preserve it and add the smallest corrective commit that lets the next
   serialized run reconcile forward. Escalate to a repository administrator
   if the observed objects disagree or inspection was incomplete.

## Published verification failed

**Symptoms:** `publish` is green; `verify-published` is red; a public tag or
release exists; `release-verification-*` reports
`published-verification-failed`.

1. Download the plan, candidate, publication, and verification artifacts.
2. Read the first failed check and compare the recorded release commit, URL,
   tag, notes digest, install result, and upgrade result with the plan.
3. Preserve all published objects. Fix the defect with a new Conventional
   Commit and let the next serialized workflow run repair forward.
4. Escalate to a repository administrator when branch protection, workflow
   permissions, or inconsistent GitHub state prevents a corrective release.

## Evidence retention

Release artifacts are retained for 14 days. Attach their names and workflow run
URL to any follow-up issue so the exact source SHA and observed remote state
remain traceable.
