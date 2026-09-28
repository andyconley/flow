# Acceptance Criteria: Review Provenance Refinement

1. `approve-review-amendment` is accepted only for a protocol-revision-2 run in `reviewing` and leaves it in `reviewing`.
2. Approval preserves the original orchestration path, bytes, and approved digest and records a distinct content-addressed replacement, dispositions artifact, and append-only digest lineage.
3. Replacement validation permits only verification corrections and appended read-only review assignments with run-local output paths; authority-expanding deltas fail closed.
4. The amendment record binds work id, original and effective paths/digests, dispositions path/digest, reason, approval time, and its own canonical digest.
5. Exact replay is idempotent; stale, conflicting, repeated, malformed, unsafe-path, symlink, out-of-state, and tampered cases do not change `run.json` or `events.jsonl`.
6. Existing revision-1, legacy, and revision-2 runs without an amendment retain existing behavior.
7. Review dispatch and orchestration validation use the approved effective manifest; Delivery charters, attempts, receipts, and historical evidence remain bound to the original manifest.
8. `accept-review` revalidates original, replacement, amendment, and disposition digests, requires non-deferred dispositions, validates acceptance, and records the amendment identity in acceptance evidence.
9. The disposition schema binds decisions to the original acceptance-criteria digest and records criterion id, controlled decision, rationale, and evidence.
10. The real MAF run records approved, bounded dispositions for AC2's v0.38 one-shot activation exception and AC13's named macOS baseline/no-new-regression rule.
11. ADR 0020, runtime installation-time wording, unsupported-host activation status, and bug-planning guidance match actual behavior.
12. Fresh quality, test, security, and SRE reviewers assess final MAF HEAD plus the amendment/dispositions; acceptance occurs only after their evidence and acceptance-stage orchestration validation pass.
13. Focused lifecycle, CLI, orchestration, tamper, compatibility, and real-run regression tests pass.

