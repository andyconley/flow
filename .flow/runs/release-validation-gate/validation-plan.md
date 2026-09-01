# Validation Plan: Automated Release Validation Gate

## Validation principles

- Prove prevention before proving success.
- Bind every result to the exact source SHA, proposed version, prior release, and workflow run.
- Use local remotes and fake publication boundaries for destructive-path tests.
- Never require a live write token to test failure behavior.
- Distinguish candidate proof, publication proof, and post-publication proof.
- Record mutation checks and any unexercised live-client limitations.

## Unit and contract validation

- Valid release-plan and release-evidence documents
- Unsupported schema versions, missing fields, wrong types, unsafe paths, invalid semver/tags/SHAs, digest mismatch, and unknown check identifiers
- Release-required, no-release, malformed-result, and empty-notes normalization
- Notes content transported safely and hashed without shell evaluation
- Exact source, prior tag, version, and notes comparisons
- Expected semantic-release generated-commit ancestry and allowed diff
- Repair-forward classification after partial or post-publication failure

## Workflow contract validation

- Jobs appear in analyze → validate-candidate → publish → verify-published order
- Candidate and publication jobs require the appropriate prior successful outputs
- Workflow defaults to read permissions
- Analyze and validation have no live write token or persisted checkout credential
- Publish alone has the current required write permissions
- No gate uses `continue-on-error`, bypass input, force push, or failure-tolerant condition
- Every checkout uses the planned SHA rather than a moving branch name
- Concurrency remains serialized with cancellation disabled
- No-release runs skip candidate, publish, and public verification

## Failure/no-write matrix

Induce failure in each stable candidate check and assert the fake publisher is never invoked:

- full test suite
- generated-help check
- staging/import check
- clean-tree check
- fresh candidate install
- candidate upgrade
- setup
- Claude sync
- Codex sync
- doctor
- static runtime smoke
- representative CLI behavior

Also reject stale `main`, changed prior tag, mismatched plan/evidence digest, changed predicted version/type/tag, changed notes digest, malformed Action output, and empty rendered notes before publication.

## Candidate integration

Using temporary homes and a local bare remote:

1. Mirror the previous published tags.
2. Add the predicted candidate tag at the exact source SHA without touching GitHub.
3. Run bootstrap release installation and assert the installed version and content.
4. Install the previous release and run `flow update` to the candidate.
5. Run machine/user setup, both sync checks, doctor, static runtime smoke, and representative CLI behavior.
6. Deliberately break staging/update and prove the previous installation remains usable.

## Policy parity

- Compare preview and publication analysis for representative `feat`, `fix`, documentation, no-release maintenance, breaking pre-1.0, and mixed commit histories.
- Assert predicted version, tag, release type, release notes, and notes digest match.
- Preserve the pinned conventional-commits renderer behavior and non-empty release notes.

## Post-publication validation

- Published version and tag match the plan
- Tag resolves to the expected generated release commit shape
- Validated source is the expected parent or ancestor
- Only configured generated files differ in the release commit
- Changelog has the expected version section
- GitHub release exists with non-empty matching notes
- Public bootstrap install selects the new tag
- Public update moves from the previous release to the new release
- Setup, both sync checks, doctor, static runtime smoke, and representative CLI behavior pass
- Any failure leaves an explicit repair-forward record

## Mutation testing

At minimum, deliberately weaken and prove detection for:

- publish dependency no longer requires candidate success
- analysis receives a live write token
- checkout changes from planned SHA to `main`
- evidence digest comparison is removed
- a candidate failure is marked `continue-on-error`
- no-release path invokes publication
- public verification failure is mislabeled as prevented publication
- shell interpolation directly evaluates release-note or artifact content

Restore the implementation after every mutation and name the failing test. Record any unrun mutation and exposed behavior.

## Repository and release validation

- Focused helper/workflow tests
- Full Python test suite
- Generated-help check
- Release-staging/transitive-import validation
- `git diff --check`
- Isolated candidate install and upgrade
- Both sync checks
- `flow doctor --check`
- Static runtime smoke
- Independent security review of permissions, tokens, artifacts, and shell boundaries
- Independent quality acceptance against the original requirements

For the transition release that introduces the gate, repeat the v0.21.0 manual pre-push checks because the old workflow cannot validate itself retroactively. After push, wait for the new workflow, verify the public artifact, and record the workflow URL, source SHA, release commit, tag, notes, changelog, installations, and limitations.

