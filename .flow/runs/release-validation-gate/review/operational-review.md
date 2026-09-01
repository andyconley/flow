# Operational Review: Release Validation Gate

Re-review of commit `298cca2`.

## Reliability Review Summary

### Service Expectations

- Healthy behavior remains one serialized release run: a non-release push is a green no-op; a release-required push reaches the one write-capable publisher only after exact-SHA candidate evidence passes; public verification determines final success after publication.
- The global `release` concurrency group uses `cancel-in-progress: false`. This correctly trades a queue for an unambiguous publisher history, avoiding cancellation midway through a possible external mutation.

### Observability Gaps

- The former P1 blocker is closed. If `Publish once` fails, the failure-only workflow path invokes `scripts/release_reconcile.py` and uploads the signed plan, candidate evidence, both pre-publish baselines, and `partial-publication.json` for 14 days. Reconciliation records `main`, the predicted tag, the GitHub release, inspection errors, classification, and a repair-forward recovery posture.
- The reconciler treats remote/API inspection faults as `inspection-incomplete` evidence rather than silently treating them as no write. That is the correct fail-safe diagnostic classification.
- Candidate evidence now verifies retained log files against their recorded SHA-256 digest before publication. This removes a gap between the evidence ledger and uploaded logs.
- Public verification still stores one structured failure record rather than separate command logs. Its first-failure detail plus GitHub Actions step log is adequate for this sequential maintainer workflow; external dashboards or paging would be disproportionate.

### Failure Modes

- Candidate validation failure: no publisher runs; the first failed check and its retained log are actionable.
- Remote baseline/repeated-analysis drift: pre-publication block; no blind retry path exists.
- Publisher failure after a possible partial write: job remains red and serialized; failure-only readback distinguishes `publication-failed-without-observed-write`, `partial-publication-observed`, and `inspection-incomplete`. The workflow neither retries semantic-release nor destroys remote state.
- Published verification failure: public objects remain preserved, verification evidence uploads before enforcement, and the job reports repair-forward rather than falsely claiming that publication was prevented.

### Deployment Safety

- **Verdict: operationally ready.** Both prior blockers are resolved without weakening the no-bypass or no-destructive-recovery contract.
- The new workflow-contract test asserts the publisher-failure condition, reconciliation script, retained artifact, single publisher invocation, and absence of force/tag/release deletion. Reconciliation unit tests cover clean, partial, and inspection-incomplete classifications.

### Operational Recommendations

- `docs/release-runbook.md` is now an actionable, symptom-first runbook for candidate failure, publisher failure/partial state, and public-verification failure. It supplies read-only confirmation commands, preservation rules, corrective-commit recovery, owner, and escalation conditions; `README.md`, the ADR, and CLI reference link to it.
- Keep the 14-day evidence retention and the current GitHub Actions failure signal. Before the transition release, a maintainer should rehearse the documented artifact inspection using the covered controlled reconciliation fixture; no real partial publication should be manufactured.

## Evidence Reviewed

- Commit `298cca2`
- `.github/workflows/release.yml`
- `scripts/release_reconcile.py`, `scripts/release_gate.py`, and `scripts/release_verify_published.py`
- `docs/release-runbook.md`, `README.md`, and `docs/adr/0002-gate-semantic-release-publication.md`
- `tests/test_release_workflow.py` and `tests/test_release_recovery.py`

Validation run: `python3 -m unittest tests.test_release_workflow.ReleaseWorkflowContractTests tests.test_release_recovery` — 16 passed.
