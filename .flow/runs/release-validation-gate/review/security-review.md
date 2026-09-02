# Security Review Summary

## Verdict

Final shipped security review passes for Flow `v0.22.0`. Hosted run
`33632240778` validated and published source
`e05178b78420db53c3f7431448e1d188cc958441`; the generated release commit is
`f5f45565c64f881f9ba07c85d23fb95e90cb292b`. All prior findings remain
resolved, and no new blocking or non-blocking security finding was found in the
hosted artifacts or public release state.

### Summary

- Critical: 0
- High: 0
- Medium: 0
- Low: 0

### Resolved Findings

#### RESOLVED Mutable action references in the write-capable job

- Location: `.github/workflows/release.yml` at every `uses:` entry;
  `tests/test_release_workflow.py:55-57,88-104`.
- Evidence: All action references now use full 40-character commit SHAs with a
  human-readable version comment. Read-only `git ls-remote` verification mapped
  the committed SHAs to the stated upstream tags:
  - `actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09` = `v5.1.0`
  - `actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444` = `v5.0.0`
  - `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02` = `v4.6.2`
  - `actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093` = `v4.3.0`
  - `cycjimmy/semantic-release-action@b12c8f6015dc215fe37bc154d4ad456dd3833c90` = `v6.0.0`
- Verification: `workflow_contract_findings` rejects any `uses:` reference that
  is not a full SHA. The focused suite passed.
- Disposition: Resolved. This closes the prior action-tag takeover path. Full
  SHA pinning follows GitHub's
  [secure use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

#### RESOLVED Candidate evidence did not bind the runner and retained logs

- Location: `scripts/release_gate.py:224-317,605-606,642-648`;
  `.github/workflows/release.yml:169-175,219-229`;
  `tests/test_release_gate.py:205-231`.
- Evidence: `validate_evidence` now requires
  `runner_sha == source_sha`; validation against the plan separately requires
  `source_sha == plan.source_sha`. The CLI requires `--logs-root`, resolves each
  validated relative log path below that root, requires a regular file, and
  recomputes its SHA-256. Both `validate-candidate` and `publish` supply
  `.release` as the root, so downloaded logs are checked before publication.
- Verification: The mismatched-runner, tampered-log, and missing-log negative
  tests passed. Direct CLI validation of the retained evidence and all thirteen
  retained logs passed.
- Disposition: Resolved for the publication authorization path.

#### RESOLVED Eight required high-risk workflow mutations were pending

- Location: `tests/test_release_workflow.py:26-58,88-104`.
- Evidence: The mutation test now changes each required property independently
  and asserts the corresponding named finding:
  - `publish-dependency`
  - `analysis-credential`
  - `exact-checkout`
  - `evidence-digest`
  - `failure-bypass`
  - `no-release-publish`
  - `public-failure-classification`
  - `notes-shell-interpolation`
- Verification: The dedicated eight-mutation test passed. It operates on an
  in-memory copy of the workflow and leaves the implementation unchanged. The
  restored workflow has no named contract finding. An additional guard rejects
  mutable action references.
- Disposition: Resolved. The durable validation-results artifact records the
  completed mutation proof.

#### RESOLVED Log-root containment allowed symlink escape

- Location: `scripts/release_gate.py:273-288`;
  `tests/test_release_gate.py:232-250`.
- Evidence: Validation resolves the evidence root, strictly resolves each log,
  rejects a resolved path outside the root, rejects a direct symlink, requires a
  regular file, and only then compares SHA-256. The controlled symlink escape
  that previously passed now raises `ContractError`.
- Verification: The dedicated symlink-escape, missing/tampered-log, and
  runner/source negative tests passed. The full focused release security,
  workflow, and recovery suite passes 52 tests at the final repair, and direct
  validation of all thirteen retained logs still passed.
- Disposition: Resolved by `ebdaf02bb62d99eff7f83edd6e7745f33be532df`.

#### RESOLVED Hosted preview Action ignored the repository URL alias

- Location: `.github/workflows/release.yml:70-81,257-268`;
  `release.config.cjs:1-11,69-73`; `tests/test_release_gate.py:392-459`;
  `tests/test_release_workflow.py:133-141`.
- Evidence: The failed hosted analysis stopped in the read-only `analyze` job
  before candidate validation or publication and made no release write. The
  repair removes the unsupported `repository_url` Action input and passes the
  canonical GitHub HTTPS URL through the preview step environment. Release
  configuration validates the complete URL against a constrained GitHub clone
  URL grammar before assigning `repositoryUrl`. It is consumed as JavaScript
  configuration data, not shell text.
- Boundary verification: The canonical value originates from
  `github.repository`, while Git access is still redirected only by a local
  `url.<file-mirror>.insteadOf` entry in the temporary preview clone. Both
  preview jobs remain without an exported `GITHUB_TOKEN`, use read-only job
  permissions, and load only the analyzer and notes plugins. Publish mode does
  not receive the preview URL override.
- Verification: The exact Action-shaped local reproduction preserved canonical
  GitHub release-note links while Git operations resolved to the local mirror.
  The invalid local-path configuration test, workflow wiring test, permission
  test, and full focused suite passed.
- Disposition: Resolved by `cad51290fd22735a46e73da901f0314d70558515`.

#### RESOLVED Candidate tests inherited host Flow state and Git identity

- Location: `scripts/release_candidate.py:258-292`;
  `tests/test_flow.py:7750-7766`.
- Evidence: The failed hosted candidate job could not satisfy the full test
  suite because tests borrowed the runner's `~/.flow/source` and Git identity.
  Publication depends on candidate success, so the failure stopped before the
  write-capable job and did not create a tag, release, or changelog commit.
- Boundary verification: The repair creates a new temporary `test-home`, points
  only its `.flow/source` at `REPO_ROOT`, and executes the full suite with
  `_clean_env(test_home)`. That helper removes `GITHUB_TOKEN`, `GH_TOKEN`, Git
  askpass variables, and repository-override variables before setting `HOME` to
  the temporary directory. `REPO_ROOT` is the script's checkout, and
  `run_candidate` has already required checkout `HEAD == plan.source_sha` before
  creating the link. The later clean-tree check still detects tracked mutations
  to that checkout. The merge-conflict fixture now supplies explicit local-only
  author and committer identity rather than depending on runner configuration.
- Verification: The full suite passed with the fake HOME, the clean detached
  candidate passed all thirteen checks, and exact-SHA evidence/log validation
  passed independently.
- Disposition: Resolved by `e05178b78420db53c3f7431448e1d188cc958441`.

### Final Hosted and Public Evidence

- GitHub Actions run
  [`33632240778`](https://github.com/andyconley/flow/actions/runs/33632240778)
  completed successfully. `analyze`, `validate-candidate`, `publish`, and
  `verify-published` all passed in dependency order.
- Hosted planned source SHA:
  `e05178b78420db53c3f7431448e1d188cc958441`.
- Candidate runner, local `main`, and local `v0.22.0` tag: all equal the planned
  source SHA.
- Previous release: `v0.21.0` at
  `f15859523ed1508aa83b5f3516ef0786c20c7ca9`.
- Predicted release: `v0.22.0`; release notes are non-empty with fifteen
  rendered entries and digest
  `a5108415ccf74682b00ad77b01e16b8db81e7656a8ba8679a1b73384402f036f`.
  The public GitHub release body hashes to the same value.
- Hosted plan digest:
  `b503b30400e1d56dec75fc850bea71dd4456eec3496ad76d8e9a12c0a1823e7d`.
- Hosted candidate-evidence digest:
  `f762fbccbc20ba8a9a01a80d88b0bfe7b51f1de2e9d9dc1e2d38911b129f2166`.
- All thirteen hosted candidate checks report `passed` with exit code zero.
- All thirteen referenced logs exist as regular, non-symlink files, resolve
  beneath the evidence root, and match their recorded SHA-256 values.
- Independent validation of the downloaded hosted plan and evidence with
  `release_gate.py`, including `--logs-root`, passed.
- Both pre-publish baselines recorded `origin/main` at the planned source,
  `v0.21.0` at its expected commit, and `v0.22.0` absent. The immediate baseline
  was captured immediately before the single successful publisher step.
- The publication artifact binds version `0.22.0`, tag `v0.22.0`, source SHA,
  release commit, and notes digest to the hosted plan.
- Public `origin/main` and public tag `v0.22.0` both resolve to
  `f5f45565c64f881f9ba07c85d23fb95e90cb292b`. That commit has exactly one
  parent—the validated source—changes only `CHANGELOG.md`, and has subject
  `chore(release): 0.22.0 [skip ci]`.
- The public changelog contains the `0.22.0` section. The GitHub release is
  published, not draft or prerelease, with the expected tag and matching notes:
  https://github.com/andyconley/flow/releases/tag/v0.22.0.
- Hosted post-publication verification passed all eleven checks: tag/generated
  commit, GitHub release/notes, public fresh install, public upgrade, setup,
  Claude and Codex sync, doctor, static runtime smoke, and representative CLI.
- Publication-result artifact digest:
  `0fbe55fa0323de8502a01b6ecadb1f355975e458fdd2571e627f2e7b5777302b`.
- Published-verification artifact digest:
  `f2606012d4542c83abcd705e89d63dc2f6342c22139ff6f00cab7f03500e26f7`.

### Positive Observations

- Workflow permissions still default to `contents: read`; only the serialized
  `publish` job raises permissions, and all checkouts disable persisted
  credentials.
- Publication requires successful candidate validation, two refreshed remote
  baselines, matching repeated analysis, and exact plan/evidence digests. There
  is no manual bypass, remote force push, tag/release deletion, or blind retry.
- The two preview actions exclude mutating plugins and use URL rewriting scoped
  to temporary clones. Release notes remain environment/file data rather than
  executable shell text.
- Publisher failure now invokes read-only reconciliation and uploads observed
  partial state for repair-forward handling; it does not rewrite or delete
  shared state.
- The candidate runner removes common GitHub/Git credential variables from
  child processes and invokes subprocesses with argv arrays.
- Focused release security, workflow, and recovery validation passed: 52 tests.

### Recommendations

- Archive the hosted plan, candidate evidence/logs, publication result, and
  published-verification artifact together as the immutable `v0.22.0` evidence
  chain.
- Keep full-SHA action pinning enforced and update pins only through reviewed
  commits.
- Preserve the existing repair-forward rule and post-write public comparison.
- Treat every later release as a new identity: generate fresh hosted plan and
  candidate evidence, refresh the live baseline, and never reuse this release's
  authorization artifacts.
