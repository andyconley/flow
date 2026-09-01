# Automated Release Validation Gate Plan

## Context

Flow v0.21.0 was released only after a manual pre-push gate proved tests, generated surfaces, release staging, installation, upgrade behavior, doctor, and runtime smoke. The repository's only GitHub Actions workflow still invokes semantic-release first and checks notes afterward. This plan turns the proven manual process into a fail-closed release workflow.

Implementation starts from `origin/main` at `2f48aad`, after v0.21.0. The canonical checkout's unrelated `docs/backlog.md` edit remains outside this work.

## Approved decisions

1. Every deterministic check used for v0.21.0 becomes a pre-publication blocker.
2. A read-only analysis step determines whether the exact pushed SHA would produce a release.
3. Non-release commits skip expensive candidate and public-artifact checks.
4. Candidate fresh-install and upgrade checks use a temporary local repository and predicted tag before publication.
5. Only the publication job receives GitHub write credentials, after candidate evidence passes.
6. Publication repeats analysis and rejects any change in SHA, prior tag, predicted version, or release-note digest.
7. Public-tag installation and upgrade remain post-publication confirmation.
8. Live client discovery and applied routing remain manual and out of scope.
9. There is no bypass. Pre-publication failures stop; post-publication failures repair forward.

## Workflow contract

### Job 1: `analyze`

- Checkout `github.sha` with full tag history and no persisted credentials.
- Build a local mirror suitable for semantic-release preview without a live write token.
- Run the same commit analyzer and release-note policy used by publication.
- Normalize the structured semantic-release result into `.release/release-plan.json`.
- Validate the plan schema and record its SHA-256 digest.
- If no release is required, finish successfully and skip the remaining jobs.

The plan records schema version, workflow/run identity, source SHA, prior release version/tag/commit, `release_required`, predicted release type/version/tag, notes digest and rendered-entry count, pinned tool/plugin versions, and creation time.

### Job 2: `validate-candidate`

- Run only when the plan says a release is required.
- Checkout the recorded source SHA, download and verify the exact plan artifact, and refuse any mismatch.
- Create a temporary local bare repository containing the previous published tags plus a local-only predicted candidate tag at the source SHA.
- Run the deterministic gate through a repository-owned runner:
  - full Python test suite
  - generated-help consistency
  - release-staging/transitive-import checks
  - clean tracked tree after generated checks
  - fresh release-mode candidate installation
  - update from the prior release to the candidate
  - machine and user setup
  - Claude and Codex sync checks
  - `flow doctor --check`
  - static runtime smoke
  - representative invocation of changed CLI behavior
- Emit `.release/release-evidence.json` plus retained logs.

Evidence records its schema version, plan digest, source SHA, candidate version/tag, candidate repository identity, each stable check id, result, exit code, duration, log path/hash, and overall result.

### Job 3: `publish`

- Depend on successful candidate validation and receive the workflow's only write-capable token.
- Re-fetch immediately and require `origin/main` to equal the planned source SHA and the latest published tag to equal the plan's prior tag.
- Verify the plan/evidence schemas and digests.
- Repeat semantic-release preview from the exact source and require version, tag, type, notes digest, and prior release identity to match the plan.
- Invoke semantic-release publication once.
- Validate its structured outputs against the plan.
- Never force-push or continue after an identity mismatch.

Because `@semantic-release/git` writes `CHANGELOG.md`, the published tag may target a generated release commit. Publication evidence records that commit and proves it descends directly from or contains the validated source with only the configured generated release change.

### Job 4: `verify-published`

- Run after successful publication with read-only permissions.
- Fetch and verify the published tag, release commit ancestry, changelog section, GitHub release, predicted version, and non-empty notes.
- In isolated homes, bootstrap-install the public tag and update from the previous public tag.
- Repeat setup, both sync checks, doctor, static runtime smoke, and a representative CLI command.
- On failure, leave the workflow red, preserve published state, record the actual tag/commit/release, and require a corrective commit.

## Repository design

### Workflow

Refactor `.github/workflows/release.yml` into the four-job dependency graph. Set workflow permissions to `contents: read`; grant `contents`, `issues`, and `pull-requests` write permissions only to `publish`, matching the current plugins. Keep one release concurrency group with `cancel-in-progress: false`.

### Shared release policy

Refactor `release.config.cjs` only as needed to let preview and publication import one analyzer, release-rule, notes, branch, tag-format, and pinned-version policy. Preview excludes live publication plugins and targets the local mirror. Publication retains changelog, Git, and GitHub plugins.

### Helpers

Add small scripts under `scripts/` for:

- normalizing and validating structured semantic-release results
- creating/verifying `release-plan.json`
- running the candidate gate and creating/verifying `release-evidence.json`
- comparing repeated analysis with the plan
- verifying the published tag/release/ancestry shape

Helpers may invoke existing tools but must not recreate semantic-release's version algorithm or parse its human-oriented log text. Validate all artifact fields and controlled values before using them in shell commands.

### Tests

Extend the existing unittest suite or add focused standard-library tests. Use local bare Git repositories, temporary homes, fixture semantic-release results, and a fake publisher boundary. Static workflow tests inspect YAML text or a safe parser without adding a production dependency unless justified.

## Implementation sequence

### Slice 1: Release contracts and shared policy

1. Define versioned plan/evidence schemas and validation helpers.
2. Extract shared release analysis and notes policy without changing behavior.
3. Add fixtures for release, no-release, malformed, empty-notes, and drift cases.
4. Record an ADR: `Gate semantic-release publication with exact-commit candidate evidence`.

Exit evidence: preview and current publication policy resolve identical versions and notes for representative commit histories.

### Slice 2: Candidate gate

1. Implement the deterministic candidate runner.
2. Build the temporary local tag/remote fixture.
3. Exercise fresh install and prior-tag update against the candidate.
4. Emit structured evidence and retained logs.

Exit evidence: the real release install/update surfaces identify the planned candidate version, and deliberate failures preserve the previous install and produce failed evidence.

### Slice 3: Workflow integration and permission isolation

1. Split the workflow into analyze, validate, publish, and verify jobs.
2. Bind every job to the plan's source SHA and artifact digest.
3. Apply read-only defaults and publication-only write permissions.
4. Add stale-plan, second-analysis, and no-bypass guards.

Exit evidence: static and fixture tests prove ordering, conditions, permissions, exact checkout identity, no-release skipping, and prevention of publisher invocation.

### Slice 4: Public-artifact verification and documentation

1. Implement tag, release, changelog, notes, ancestry, install, and upgrade checks.
2. Preserve the current non-empty-notes detection within the expanded verifier.
3. Document pre-publication blockers, post-publication checks, manual limitations, evidence, and repair-forward operations.
4. Update architecture, CLI/release guidance, and the capability-gap disposition when complete.

Exit evidence: fixture and controlled workflow tests distinguish prevented publication from a published artifact that subsequently failed verification.

### Slice 5: Acceptance and full release

1. Run focused tests, the full suite, generated-help, staging, candidate install/update, doctor, sync, runtime-smoke, and mutation checks.
2. Have an independent security reviewer inspect token boundaries, artifact injection, shell handling, and write paths.
3. Have an independent quality reviewer accept the workflow against the original criteria.
4. Integrate without force, inspect the remote and staged paths, and confirm `docs/backlog.md` is absent.
5. Commit with Conventional Commits and push to `main`.
6. Observe the new workflow prove its own release candidate before publishing.
7. Verify the public release and record tag, commit, workflow URL, changelog, notes, installation, and upgrade evidence.

Exit evidence: the released workflow itself blocks publication until deterministic evidence passes, and the resulting public artifact passes the post-publication checks.

## Explicit exclusions

- Live Claude/Codex discovery and applied model/effort verification
- External provider identity or actual capability-grant proof
- New semantic version rules
- General PR validation policy
- Release deletion, tag rewriting, force-push, or automatic rollback
- Manual bypass controls
- Unrelated canonical-checkout changes

## Known risks

- Release-producing runs take materially longer.
- A flaky deterministic check blocks publication by design.
- Preview and publication can drift if shared policy or exact-SHA checks are incomplete.
- Semantic-release publication is not transactional; partial success requires state inspection and repair forward.
- The new workflow must prove itself while changing the mechanism that publishes it, requiring a documented manual pre-push gate for this transition release.

