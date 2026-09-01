# Security Review Summary

## Verdict

Security review passes for commit
`ebdaf02bb62d99eff7f83edd6e7745f33be532df`. All prior findings are resolved;
no blocking or non-blocking security finding remains.

Publication is still contingent on regenerating the release plan and candidate
evidence for the current HEAD. The retained plan/evidence were produced for
`777670320a65ec713947bea7ca043d3321b5cee0`, before the remediation commits, so
they are valid historical evidence but cannot authorize release of `ebdaf02`.

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
- Disposition: Resolved. The durable validation-results artifact should be
  updated from “pending” before handback, but the proof itself ran successfully
  during this independent review.

#### RESOLVED Log-root containment allowed symlink escape

- Location: `scripts/release_gate.py:273-288`;
  `tests/test_release_gate.py:232-250`.
- Evidence: Validation resolves the evidence root, strictly resolves each log,
  rejects a resolved path outside the root, rejects a direct symlink, requires a
  regular file, and only then compares SHA-256. The controlled symlink escape
  that previously passed now raises `ContractError`.
- Verification: The dedicated symlink-escape, missing/tampered-log, and
  runner/source negative tests passed. The full focused release security,
  workflow, and recovery suite passed 50 tests, and direct validation of all
  thirteen retained logs still passed.
- Disposition: Resolved by `ebdaf02bb62d99eff7f83edd6e7745f33be532df`.

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
- Focused release security, workflow, and recovery validation passed: 50 tests.

### Recommendations

- Regenerate the plan, candidate evidence, and logs against commit `ebdaf02` (or
  the final reviewed release SHA) before any publication attempt.
- Update `validation-results.md` to record the completed eight-mutation proof and
  the final focused/full-suite results.
- Keep full-SHA action pinning enforced and update pins only through reviewed
  commits.
- Preserve the existing repair-forward rule and post-write public comparison.
