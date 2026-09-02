# Test Validation: Release Validation Gate

## Verdict

**PASS — shipped and publicly verified.** Hosted run
[`33632240778`](https://github.com/andyconley/flow/actions/runs/33632240778)
released `v0.22.0` from validated source
`e05178b78420db53c3f7431448e1d188cc958441`. The workflow completed its
candidate gate before publication and its public verifier after publication.
All retained hosted artifacts validate and the live GitHub tag/release agree
with them.

## Test Coverage Analysis

### Current Coverage

- Hosted `analyze` produced a release-required plan for `v0.22.0`, source
  `e05178b...`, and prior release `v0.21.0`. The retained plan digest is
  `b503b304...`.
- Hosted `validate-candidate` passed all **13/13** deterministic checks. The
  retained evidence binds its source, runner, candidate-main, and local-only
  candidate-tag SHA to `e05178b...`; retained log hashes validate. Its Python
  suite log records **770 tests passed**.
- Both hosted pre-publication baseline artifacts record `main` at `e05178b...`,
  latest tag `v0.21.0`, and an absent candidate tag before the one publisher
  invocation.
- The publication result matches the plan's version, tag, source, and notes
  digest. It created release commit
  `f5f45565c64f881f9ba07c85d23fb95e90cb292b`; that commit has the validated
  source as its sole parent and changes only `CHANGELOG.md`.
- Live readback confirms `main` and `refs/tags/v0.22.0` resolve to
  `f5f45565...`; the public [GitHub release](https://github.com/andyconley/flow/releases/tag/v0.22.0)
  exists with non-empty notes. The release notes digest agrees with the plan and
  publication artifact.
- Hosted `verify-published` passed all **11/11** checks: tag/generated commit,
  GitHub release/notes, public fresh install, public upgrade, machine and user
  setup, Claude and Codex sync checks, doctor, static runtime smoke, and
  representative CLI behavior. Its retained evidence digest is `f762fbcc...`.
- Local test validation remains green: workflow/gate contracts (45 tests),
  candidate integration including all thirteen injected-failure paths (3 tests),
  and recovery tests (7 tests). The workflow mutation matrix detects all eight
  required unsafe source changes.

### Remaining Gaps

- None that block this release. The candidate and public verifier use isolated
  environments; telemetry history and real interactive Claude/Codex client
  sessions remain intentionally outside deterministic CI and are documented
  operational limitations, not release-gate failures.

## Verification Notes

- Artifact integrity was rechecked with `validate-plan` and
  `validate-evidence --logs-root` against the hosted plan, evidence, and logs.
- The hosted public verifier is the authoritative proof for the published tag,
  release, consumer install, and upgrade paths. Future failures remain
  repair-forward events under `docs/release-runbook.md`; no delete, rewrite, or
  blind retry path is authorized.
