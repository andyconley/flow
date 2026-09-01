# Implementation Sequencing: Automated Release Validation Gate

## Current seams to reuse

- `.github/workflows/release.yml` is one serialized `main` push workflow. Preserve its existing concurrency group and its semantic-release version/plugin pins, but move write permissions and `GITHUB_TOKEN` to a single downstream job.
- `release.config.cjs` is the authoritative release-rule, tag-format, and notes-rendering policy. Split its configuration into importable policy and publication-plugin assembly; do not duplicate `releaseRules` or note types in a preview helper.
- `install.sh`, `install-flow.sh`, and `cli/lifecycle.py` already implement the actual consumer paths. The candidate and public checks should drive these surfaces using `FLOW_REPO_URL` or `flow update --remote`, not re-create installation logic.
- `tests/test_flow.py` already supplies temporary homes, local bare Git remotes, install helpers, and update tests. Extend that harness or extract a narrowly-scoped release-gate test utility rather than adding a second fixture system.
- `cli/lifecycle._validate_staging`, `flow doctor --check`, `flow runtime smoke`, and the generated-help/sync commands are the existing deterministic checks. A release-gate runner should invoke them and record outcomes, not copy their internals.

## Change surface and helper boundaries

| Area | Change | Boundary / interface |
| --- | --- | --- |
| `release.config.cjs` | Export one policy factory plus separate preview and publication plugin lists. | `createReleaseConfig({ mode: "preview" | "publish", repositoryUrl })`; preview excludes changelog/git/GitHub mutation plugins while retaining analyzer and notes generator settings. |
| `scripts/release-gate-lib.mjs` | New pure, testable contract and comparison library. | `normalizeAnalysis(result, context)`, `validatePlan(plan)`, `validateEvidence(evidence)`, `sha256(value)`, `compareAnalysis(plan, analysis)`, `verifyReleaseCommitShape(...)`. All failures are typed/error-coded and no method executes shell input. |
| `scripts/release-analyze.mjs` | New read-only semantic-release adapter. | Writes `release-plan.json` and a digest file from structured API/action output; accepts SHA, prior-release identity, local mirror URL, run identity, and output path. It never accepts a live GitHub token or parses console text. |
| `scripts/release-candidate.mjs` | New deterministic candidate runner. | Builds local bare candidate remote and tag, executes named check commands with argument arrays, writes per-check logs and `release-evidence.json`; returns nonzero on first failed required check after recording evidence. |
| `scripts/release-publish-guard.mjs` | New pre-write guard. | Validates artifact schemas/digests, fetches live baseline, repeats analysis, and emits only validated values to `GITHUB_OUTPUT`/environment files. It never publishes itself. |
| `scripts/release-verify-published.mjs` | New post-write verifier. | Reads tag/release/notes through Git/GitHub CLI or API boundary, checks expected release-commit ancestry/diff, then drives public install and upgrade checks in temporary homes. Emits repair-forward classification on failure. |
| `.github/workflows/release.yml` | Four-job DAG: analyze -> validate-candidate -> publish -> verify-published. | Artifact names contain plan/evidence plus SHA-256 digest; all checkout refs come from plan output, never `main` after analysis. |
| `tests/test_release_gate.py` (preferred) | Focused standard-library tests for helpers, local remotes, and workflow contract. | Keep broad CLI regression coverage in `tests/test_flow.py`; new file avoids turning that large file into an unrelated CI parser. |
| `docs/adr/0002-gate-semantic-release-publication.md`, `README.md` | Decision, operations, and user-facing release explanation. | Distinguish blocker checks from published-artifact verification and manual client limitations. |

The exact semantic-release adapter must be prototyped first. The current repository has no checked-in Node package manifest; semantic-release presently arrives through `cycjimmy/semantic-release-action@v6`. The implementation must establish a supported, pinned way to obtain a structured preview result (for example, a local temporary Node install used by both preview and publish wrappers, or documented Action outputs). Do not assume a dry run exposes all required fields until a fixture/controlled invocation proves it. If the Action only exposes human logs, stop and change the adapter design rather than scraping them.

## Incremental execution and commit boundaries

1. **Release-policy and contract slice**
   - Add the reusable policy factory and contract library; keep the existing workflow untouched.
   - Add fixtures for release, no-release, malformed result, empty notes, changed prior tag, and mismatched notes/version/type.
   - Add helper tests proving schema/version validation, safe value handling, canonical hashing, and preview/publish policy parity across `feat`, `fix`, docs, pre-1.0 breaking, and no-release histories.
   - Record ADR 0002 with the generated-commit ancestry exception and repair-forward rule.
   - Commit boundary: `feat(release): add validated release planning contracts` (feature because it creates the maintainers' release-safety capability).

2. **Candidate gate slice**
   - Implement local bare remote creation from a checked source SHA, copying prior tags and creating the local-only candidate tag.
   - Implement command execution as argument arrays with controlled environment and per-check log files. Stable IDs: `python-tests`, `generated-help`, `release-staging`, `clean-tree`, `fresh-install`, `upgrade`, `setup-machine`, `setup-user`, `sync-claude`, `sync-codex`, `doctor-check`, `runtime-smoke`, `representative-cli`.
   - Reuse test harness temporary homes and fake remotes for a real `install.sh` fresh install and old-tag `flow update` upgrade.
   - Test every individual injected failure produces failed evidence and never calls a fake publisher; include rollback/usability proof for a failed staged update.
   - Commit boundary: `feat(release): validate local release candidates`.

3. **Workflow/permission slice**
   - Refactor workflow to global `contents: read`, read-only analyze/candidate/verify jobs, and publication-only `contents`, `issues`, `pull-requests` write permissions and token.
   - `analyze` checks out `github.sha` with `persist-credentials: false`, emits a no-release boolean and plan digest, then uploads a plan artifact.
   - `validate-candidate` checks out only the plan's SHA, validates the downloaded plan, uploads evidence/logs, and is conditionally skipped on no release.
   - `publish` consumes both artifacts, refreshes `origin/main` and previous tag, repeats analysis, compares all identities/digests, then invokes semantic-release once. Capture structured post-publish outputs without exposing release notes to shell evaluation.
   - Static tests inspect workflow text/structure for dependency graph, all conditions, exact checkout references, token scope, no credentials in pre-publish jobs, no `continue-on-error`, no bypass input, and retained concurrency settings.
   - Commit boundary: `ci(release): gate publication on candidate evidence`.

4. **Public verification and operations slice**
   - Implement tag/release/changelog/note checks and release-commit shape proof: tag target contains the validated source, and the generated release commit changes only configured release files (currently `CHANGELOG.md`) with the expected message shape.
   - Reuse the candidate runner's install/setup/sync/doctor/smoke command construction with a public remote mode, but create an explicit result classification: `published-verification-failed`, never `publication-prevented`.
   - Add documentation of artifacts, failure classes, evidence retention, fresh baseline before write, and corrective-commit-only recovery.
   - Commit boundary: `feat(release): verify published release artifacts` plus a separate `docs(release): document release gate operations` if the documentation is substantial enough to review independently.

5. **Integration/release slice (no code mixing)**
   - Run focused tests, full Python suite, generated-help, `git diff --check`, staging, isolated candidate install/upgrade, setup/sync/doctor/runtime/CLI checks, and all named mutation checks.
   - Obtain independent security and quality review after the workflow is complete, remediate in new conventional commits, then repeat affected evidence.
   - For the transition release, manually execute the same pre-push gate because the old one-job workflow cannot enforce this new gate. Immediately before shared mutation, refresh branch/tag/release baseline and verify the unrelated canonical `docs/backlog.md` edit is not present.
   - Push only the reviewed feature commits without force. The new workflow owns the resulting tag/release/changelog mutation; observe it and perform readback comparison. Any partial or public-verification failure is a red result with a corrective follow-up commit, never a deletion or retry bypass.

## Sequencing constraints and pitfalls

- **Structured semantic-release result is the first technical spike.** The rest of the design depends on extracting release-required/type/version/notes from a supported API. No helper may calculate these independently or parse stdout.
- **Do not tag the source in the primary worktree.** Candidate tags belong exclusively in an isolated local bare remote. Candidate installation must pass that remote URL through existing installer inputs.
- **Treat artifacts as hostile data.** Validate schema, SHA, semver/tag grammar, paths relative to a known artifact root, and fixed check IDs before use. Use Node/Python process argument arrays and GitHub environment/output files; never interpolate notes, tags, or log paths into executable shell syntax.
- **The `@semantic-release/git` release commit is not a source-SHA equality case.** Verify ancestry and a constrained diff/message instead; otherwise legitimate publishes fail. Conversely, do not accept arbitrary descendants.
- **Avoid a moving ref race.** Every downstream checkout uses plan `source_sha`; publish must independently confirm remote `main` and latest tag remain the recorded values after downloading artifacts and immediately before calling semantic-release.
- **No-release must be an explicit green terminal path.** Make its output boolean/data contract testable; relying solely on a skipped semantic-release Action output can accidentally run a downstream job on an empty string.
- **The candidate runner must not conceal failures.** It needs retained logs and a failed evidence document even when the first deterministic check fails; no `continue-on-error` or catch-and-green behavior.
- **A release changes its own workflow.** The transition release needs manual evidence in the run artifacts. Later releases prove the automated gate, but that does not retrospectively validate the transition.
- **Keep `docs/backlog.md` exclusion mechanical.** Work only in the isolated worktree and check both staged and outgoing diffs before each commit/push.

## Verification order

1. Pure contract/policy tests and preview parity fixtures.
2. Local bare-remote candidate tests, including fresh install and upgrade.
3. Static workflow contract and injected publisher/no-write tests.
4. Public verifier fixture tests, including permitted and forbidden generated-release diffs.
5. Full repository suite plus deterministic command gate against the changed tree.
6. Eight specified mutation tests, restoring each mutation before the next.
7. Independent security/quality reviews.
8. Transition manual pre-push gate, serialized publish, workflow observation, public install/upgrade readback, and recorded repair-forward status if necessary.

## Definition of done for implementation sequencing

The workflow should stay intentionally thin: orchestration and credentials in YAML; release policy, data validation, Git operations, and check execution in tested helpers. That division makes ordering/permission changes statically reviewable and lets most negative paths run entirely against temporary repositories without publishing a real release.
