# Implementation Architecture: Release Validation Gate

## Recommended implementation shape

Keep semantic-release as the authority for commit analysis, version selection, and release-note rendering. Use the existing `cycjimmy/semantic-release-action@v6` twice in preview mode and once in publication mode, with a thin repository helper that turns the Action's structured outputs into validated JSON contracts. Do not parse semantic-release logs and do not duplicate its release algorithm.

The four jobs remain `analyze -> validate-candidate -> publish -> verify-published`. The plan and evidence files are the authoritative handoffs between jobs; job outputs carry only small routing and integrity values.

## Shared policy boundary

The smallest safe refactor is to make `release.config.cjs` expose one shared analysis policy and select only the side-effecting tail by an explicit preview mode:

- Shared in both modes:
  - `branches: ["main"]`
  - `tagFormat: "v${version}"`
  - the complete `@semantic-release/commit-analyzer` configuration and release rules
  - the complete `@semantic-release/release-notes-generator` configuration and visible type sections
- Publication only:
  - `@semantic-release/changelog`
  - `@semantic-release/git`
  - `@semantic-release/github`

Implement this as immutable constants plus plugin factory functions in one CommonJS module. Either keep the factories in `release.config.cjs` or move them to `release.policy.cjs` and have `release.config.cjs` import them. A separate policy module is preferable because focused tests can import it without loading publication configuration. Factory functions should return fresh arrays and option objects so plugin initialization cannot mutate shared configuration between invocations.

Use a controlled value such as `FLOW_RELEASE_MODE=preview|publish`. Refuse an unknown value. Defaulting to publication is compatible with semantic-release's current invocation, but the repository wrapper should always set the mode explicitly. Preview must contain only the analyzer and notes plugins. Publication must contain the same two plugin instances followed by the current changelog, Git, and GitHub plugins in their current order.

Do not create separate handwritten preview and publication rule sets. Tests should compare their first two normalized plugin configurations byte-for-byte and cover the existing `feat`, `fix`, documentation, breaking pre-1.0, mixed, and `chore(release)` histories.

The semantic-release and plugin pins currently live in workflow inputs rather than the release configuration. Keep those pins unchanged for this slice. Put the repeated `semantic_version` and `extra_plugins` values in one YAML anchor if GitHub Actions accepts the final form cleanly; otherwise repeat them and add a static test that both preview invocations and publication use identical pins. Avoid adding a package manifest solely to call semantic-release directly unless the Action proves unable to return a usable structured dry-run result.

## Credential-free semantic-release preview

Semantic-release dry-run still verifies that it can push to `repositoryUrl`. Running it against GitHub without a token therefore violates the approved permission boundary. The preview should instead use a temporary writable local bare repository:

1. Checkout `${{ github.sha }}` with `fetch-depth: 0` and `persist-credentials: false`.
2. Verify `git rev-parse HEAD` equals `${{ github.sha }}`.
3. Create a bare repository under `${{ runner.temp }}`.
4. Push the checked-out HEAD into that repository as `refs/heads/main` and copy all fetched release tags into it. This is a local mutation only.
5. Verify the local bare repository's `refs/heads/main` resolves to the source SHA and its latest valid Flow release tag matches the checkout's latest release tag.
6. Run the Action with:
   - `dry_run: true`
   - `repository_url: file://<absolute-local-bare-path>`
   - `FLOW_RELEASE_MODE=preview`
   - no `GITHUB_TOKEN`, `GH_TOKEN`, persisted checkout credential, or job write permission

Core semantic-release then performs its push-permission probe against the local bare repository. The preview plugin list contains no Git or GitHub publication plugin, so it has no live external write surface. Keep `ci: true`: the temporary remote has `main` at the exact pushed SHA, so branch/head validation should pass rather than being disabled. If the Action has trouble with the detached checkout, run it from a temporary working clone of the local bare repository with `main` checked out; do not weaken the check with `ci: false` as the first remedy.

Run a focused integration test against a local bare repository before wiring the workflow. It must prove that a release result contains the expected prior release and `nextRelease`, and that a no-release history returns no result, with all GitHub credential variables absent.

### Structured preview result

Use Action outputs, not console prose. In dry-run mode the Action's `new_release_published` output is poorly named: its implementation sets it to `"true"` whenever semantic-release returns a `nextRelease`, even though dry-run skipped prepare and publish. Normalize it to `release_required`; never record it as publication evidence.

The useful structured outputs are:

- `new_release_version`
- `new_release_git_tag`
- `new_release_git_head`
- `new_release_notes`
- `last_release_version`
- `last_release_git_tag`
- `last_release_git_head`

The Action does not expose `nextRelease.type`. The helper may derive `major|minor|patch` by comparing validated prior and next semantic versions; that is classification of an already selected version, not reimplementation of semantic-release analysis. Reject any version transition that cannot be classified. For a no-release result, require all `new_release_*` outputs to be absent and record `release_required: false`.

Pass every multiline or potentially attacker-controlled Action output to the helper through environment variables. Never interpolate notes into a `run:` script. The helper computes the notes SHA-256 and rendered-entry count and writes only normalized fields to `release-plan.json`. The raw notes may be retained as a separate non-executable artifact if later byte comparison needs them; the plan needs only their digest and count.

## Contract helper boundary

A repository-owned standard-library helper should own:

- normalization of structured Action outputs
- strict validation of source SHA, full Git SHAs, semantic versions, `vN.N.N` tags, release type, run identity, and controlled check identifiers
- `release-plan.json` creation and verification
- `release-evidence.json` creation and verification
- canonical JSON serialization and SHA-256 calculation
- original-versus-repeated preview comparison
- published Git/tag/commit-shape verification

It must not:

- analyze commit messages
- select a release version
- render release notes
- parse semantic-release logs
- invoke a live publisher during tests

Canonical serialization should be UTF-8 JSON with sorted keys and fixed separators/newline behavior. Validate first, then calculate the canonical digest. Reject extra top-level fields unless an explicit compatibility policy is added; accepting arbitrary fields makes the digest contract harder to reason about.

## Workflow artifact and output transport

Upload the plan even for a no-release run so the no-op decision is auditable. Use a fixed artifact name incorporating trusted workflow identity, for example `release-plan-${{ github.run_id }}-${{ github.run_attempt }}`. Set `if-no-files-found: error` and a finite retention period.

The `analyze` job should expose only:

- `release_required`
- `plan_artifact_name`
- `plan_sha256`
- `source_sha`

Downstream conditions may use `release_required`, but every downstream job must download the exact named artifact, validate its schema, recompute its digest, and compare its internal source SHA with both the job output and the checked-out commit. Treat job outputs as routing hints; treat the validated artifact as the evidence record.

The candidate job uploads a second uniquely named artifact containing `release-evidence.json` and per-check logs. Its job outputs should be limited to the evidence artifact name and evidence digest. The evidence document includes the plan digest, making the chain explicit:

`workflow SHA -> release plan digest -> candidate evidence digest -> publication result`

Do not transport the JSON document or notes through job outputs. Job outputs are awkward for multiline data and make truncation/escaping errors easy. Download artifacts by exact name rather than wildcard. The publication job must validate both artifacts before it receives or uses any field as a command argument.

The workflow should declare `permissions: contents: read` at top level. `analyze`, `validate-candidate`, and `verify-published` inherit read-only permissions and use `persist-credentials: false`. Only `publish`, after `needs: [analyze, validate-candidate]`, receives `contents: write`, `issues: write`, and `pull-requests: write`. Only semantic-release receives `GITHUB_TOKEN` in that job.

## Publication mechanics and drift guards

The publication job should perform these operations in order:

1. Checkout the planned source SHA with full history and no persisted credential.
2. Validate plan and evidence and require `overall_result == "passed"`.
3. Fetch `origin/main` and tags immediately before analysis.
4. Require `origin/main == plan.source_sha` and the prior release tag/version/commit to match the plan.
5. Rebuild a new local preview mirror from this checkout.
6. Repeat credential-free preview with the shared preview policy.
7. Require exact agreement on source SHA, prior release identity, next version, tag, derived type, notes digest, and rendered-entry count.
8. Invoke publication once with `FLOW_RELEASE_MODE=publish` and the live repository URL/token.
9. Normalize its structured result into a publication-result artifact and compare version, tag, and notes digest with the plan.

Do not compare preview and publication `new_release_git_head` for equality. Preview runs before the changelog prepare step, while publication uses `@semantic-release/git`, which creates a generated release commit. The final tag is therefore expected to peel to that generated commit, not necessarily to `plan.source_sha`.

The final remote-ref check narrows but cannot eliminate the race between checking `origin/main` and semantic-release's push. A concurrent branch advance must produce an ordinary non-fast-forward failure. Never retry automatically, force, or reuse stale evidence. Because the workflow concurrency group is serialized with `cancel-in-progress: false`, a newer queued run can analyze the cumulative state after the stale run stops.

## Expected `@semantic-release/git` commit verification

With the current plugin order and configuration, the expected successful shape is strict:

- the predicted tag peels to one commit, `release_commit`
- `release_commit` has exactly one parent
- that parent is exactly `plan.source_sha`
- `origin/main` resolves to `release_commit` after publication
- `git diff-tree` from the parent to `release_commit` reports exactly `M CHANGELOG.md`
- the subject is exactly `chore(release): <version> [skip ci]`
- `CHANGELOG.md` contains the new `## [<version>]` section
- the GitHub release exists for the predicted tag and has non-empty notes matching the planned notes digest

The v0.21.0 release demonstrates this current shape: tag `v0.21.0` peels to release commit `f158595`, whose only parent is validated source `c1577f4`; its only changed path is `CHANGELOG.md`.

Prefer the direct-parent rule over a loose ancestor rule. The pre-publication branch guard gives semantic-release a checkout whose HEAD is the planned SHA, and `@semantic-release/git` is configured to create one release-assets commit. An intermediate commit indicates drift or a changed plugin contract and should fail closed. If the configured Git assets change in the future, update the shared allowed-assets policy and its tests deliberately rather than accepting arbitrary generated paths.

Do not enforce bot author name/email as a safety invariant; those are configurable environment defaults and do not describe content integrity. Do enforce parent count, parent identity, allowed path/status, tag, version, subject, changelog section, and notes digest.

Publication is not transactional. The Git plugin can push the release commit/tag before the GitHub release plugin finishes. If semantic-release returns failure, run read-only reconciliation against `origin/main`, the predicted tag, and the GitHub release API and record which writes exist. Never invoke semantic-release again blindly. Any partial or post-publication failure is repair-forward work.

## Candidate tag boundary

The local candidate repository should use the same predicted tag but remain structurally isolated from the live remote. Its `main` and predicted tag both point to `plan.source_sha`; it does not contain the not-yet-created changelog release commit. This is correct candidate evidence for install/update behavior. The public verifier separately proves the final generated release commit and hosted tag.

Set `FLOW_REPO_URL=file://<candidate-bare-repository>` so the real `install.sh` resolves and clones the candidate tag. For upgrade validation, install the prior public tag into an isolated home, point update at the local candidate repository, and require the installed version to advance to the predicted tag. Verify the previous installation remains usable after an induced staging/update failure.

## Tests needed around these boundaries

- Preview with no GitHub token succeeds against a local bare remote for release and no-release histories.
- Preview and publication configurations share identical analyzer and notes policy.
- Unknown `FLOW_RELEASE_MODE` is rejected; preview cannot load changelog/Git/GitHub plugins.
- Dry-run `new_release_published=true` normalizes to `release_required=true`, never `published=true`.
- Malformed/missing Action outputs and empty rendered notes fail before candidate execution.
- Artifact digest, source SHA, prior tag, version, type, tag, and notes drift fail before the publisher boundary.
- Job-output tampering cannot override a contradictory plan artifact.
- Notes containing shell syntax remain inert through environment/file transport.
- Published-tag verification accepts the exact one-parent/one-`CHANGELOG.md` commit shape and rejects an extra parent, wrong parent, extra file, wrong status, wrong subject, wrong tag, or mismatched notes.
- Partial publication states are classified without deletion, rewrite, or automatic retry.

## Implementation cautions

- GitHub Action tags such as `@v6`, `@v5`, and `@v4` are mutable major references. Pinning Actions to full commit SHAs would reduce supply-chain risk, but that is broader than the stated semantic-version-policy constraint. Record it as a security-review decision rather than silently expanding this slice.
- The release commit contains `[skip ci]`, so GitHub can suppress the workflow triggered by that generated commit before the workflow-level condition is evaluated. The source run must therefore retain all publication and post-publication evidence; do not depend on a second workflow run for the release commit.
- Never use a release note, artifact path, tag, or version until the helper has validated it. Pass validated values as discrete process arguments, not assembled shell fragments.
- Do not call public verification a pre-publication guarantee. Candidate evidence proves the source-shaped local artifact; hosted-tag verification proves the final public artifact.
