# Operational Review: Release Validation Gate

Final shipped review for `v0.22.0`.

## Reliability Review Summary

### Service Expectations

- Healthy release behavior is now demonstrated end-to-end: one serialized release run evaluates the exact source SHA, admits publication only after candidate evidence passes, publishes exactly one generated release commit and tag, then verifies the public result.
- Hosted run `33632240778` completed all four jobs successfully for source `e05178b78420db53c3f7431448e1d188cc958441`: analysis, candidate validation, publication, and published verification. It created `v0.22.0` and release commit `f5f45565c64f881f9ba07c85d23fb95e90cb292b`.
- The public verifier reports `published-verification-passed` with all 11 checks passed, including fresh install, upgrade, machine and user setup, Claude and Codex sync, doctor, runtime smoke, and representative CLI behavior.

### Observability Gaps

- The release has durable, correlated evidence: hosted plan digest `b503b30400e1d56dec75fc850bea71dd4456eec3496ad76d8e9a12c0a1823e7d`, candidate-evidence digest `f762fbccbc20ba8a9a01a80d88b0bfe7b51f1de2e9d9dc1e2d38911b129f2166`, publication result, retained check logs, and public-verification result are preserved with the run artifacts.
- Failure-only reconciliation remains available for an interrupted publisher. It records remote main/tag/release state and intentionally classifies unavailable remote inspection as `inspection-incomplete`, not as an absence of writes.
- A separate service dashboard or paging policy is still unnecessary for this maintainer-operated release workflow. GitHub Actions failure status, the structured artifacts, and the symptom-first runbook are actionable at this criticality.

### Failure Modes

- The gate failed closed twice before the successful release without creating a tag or GitHub release: run `33564014091` stopped during read-only analysis because the preview URL was not canonical; run `33565098215` stopped during candidate validation because tests inherited runner-local state. Both faults were repaired forward in source (`cad5129`, then `e05178b`) and their evidence was retained.
- Candidate-validation, baseline-drift, and repeated-analysis failures still prevent the sole write-capable publisher from running.
- A publisher failure after a possible external write remains a red, serialized condition. The workflow preserves evidence, performs read-only reconciliation, and requires a corrective commit or explicit maintainer decision; it never retries semantic-release blindly or deletes tags/releases.
- A post-publication verification failure likewise preserves the public objects and reports repair-forward recovery rather than pretending publication was prevented.

### Deployment Safety

- **Verdict: shipped and operationally ready.** The successful release had no unexpected remote delta: the generated release commit is a child of the exact source SHA, and publication produced the expected `v0.22.0` release.
- The workflow's serialized release concurrency (`cancel-in-progress: false`), immutable action pins, read-only defaults, and isolated candidate test environment remain the effective safeguards against concurrent or environment-dependent release behavior.
- External GitHub artifact-action Node 20 deprecation warnings were non-blocking in this run. Track their upstream migration, but they did not affect the gate result or require release recovery.

### Operational Recommendations

- Keep the 14-day release-evidence retention and use [the release runbook](../../../../docs/release-runbook.md) for candidate, publisher/partial-state, and published-verification failures.
- Do not manufacture a real partial publication. Continue using the covered reconciliation fixtures to rehearse artifact inspection and recovery decisions.
- For a live incident, confirm remote state with the runbook's read-only commands before any corrective commit; retain the failed-run artifacts and escalate if reconciliation reports `inspection-incomplete`.
- The hosted public verifier is strong release evidence but does not replace a manual operator check of user-specific credentials or local custom configuration after a real-world support report.

## Evidence Reviewed

- Hosted workflow run `33632240778`: [successful workflow](https://github.com/andyconley/flow/actions/runs/33632240778)
- Published [v0.22.0 release](https://github.com/andyconley/flow/releases/tag/v0.22.0)
- `release-publication-33632240778-1/publication-result.json`
- `release-verification-33632240778-1/published-verification.json`
- Retained safe-failure runs `33564014091` and `33565098215`
- `docs/release-runbook.md`, `scripts/release_reconcile.py`, and the release workflow contracts
