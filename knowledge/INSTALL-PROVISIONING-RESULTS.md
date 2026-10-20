# Install/update provisioning correction (unreleased)

Normal install/update now gates runtime activation on local knowledge readiness. It reuses compatible assets, asks for missing-asset download consent on a terminal (including /dev/tty for piped bootstrap), and runs the shared verified provisioning followed by synchronous snapshot build/audit. Explicit `--knowledge download|offline|defer` and `--non-interactive` modes avoid prompting; JSON mode does too. Metadata-only `--check` never provisions. Setup is retained for repair/advanced offline transfers.

No chat weights, agent-provider changes or credential copies are introduced. Existing configuration wins; cached verified assets remain durable outside runtime installs. Explicit deferral returns `ready: false`, prints its agent-launch impact and provides `flow update --knowledge download` as the normal resume command.

## Transaction and review evidence

- 248 tests passed in the final consumer-policy regression run with seeded HOME and all local fixture flags enabled. New tests cover consent, absent terminal, piped-bootstrap controlling terminal, decline/defer/offline/noninteractive/JSON policy, no-op catch-up, model/dependency/snapshot failure, provider preservation, manual edit/deletion/config preservation, writer exclusion, complete rollback inventory, activation-time edits, same-version provisioning receipts, uncertain cancellation and pre-activation finalization failure.
- The existing distribution fixture executes the staged installed helper with explicit deferred/no-model policy using a real interpreter. Dependencies/npm are fixture controlled. Full fresh online knowledge acquisition/model execution is not claimed.
- Independent read-only review identified and verified fixes for restoration races, intended-byte audit, incomplete rollback checks, stale no-op receipts, cancellation uncertainty, post-activation finalization and late manual edits. No remaining substantiated blocker was reported after rechecks.
- Final full log: `knowledge/evidence/install-update-final-regressions.log`. No large downloads, live models, active installation changes or credential copying were used.

The installer holds the knowledge writer lock across the staged subprocess via a validated inherited descriptor. Immutable assets/generations remain cached. Mutable authority/configuration and snapshot selection are backed up; failures restore only installer-owned mutations, preserving unexpected manual bytes/deletions. Successful manual changes are included in the rollback baseline; later edits cause rollback refusal. A frozen finalized inventory prevents activation-time edits from being misclassified as installer-owned.

Cancellation observes only owned descendants. A bounded failure stops/reaps them before restoration. Uncertain observation/termination retains process identity/audit/result evidence, skips restoration and blocks retry/agent launch pending explicit reconciliation. It does not blindly retry a potentially live writer. New operations reject active knowledge writers.

## First upgrade from v0.52.0

The v0.52.0 installed updater cannot execute a hook it does not contain. Once this correction is released, that first transition must use the current public bootstrap over the existing install, with interactive consent or an explicit knowledge policy. Subsequent normal `flow update` runs use the integrated gate. An old v0.52.0 `flow update` alone cannot retroactively prompt/provision; this remains an explicit migration limitation for parent review.

## Release status and parallel scope

This is a separate correction to v0.52.0, with no tag/release rewriting and no merge/release yet. The separate smoke-recovery task owns lifecycle/glg/preflight/handoffs. This branch does not edit those files; it calls the existing ProcessScope API, which must remain compatible at integration.

Hosted head836a0a7 built the runtime but the separate verify_v2_consumer harness omitted an explicit unattended knowledge policy. It correctly failed consent. Both harness install calls now explicitly defer and assert visible deferral; existing consumer assertions remain intact. Negative hosted evidence is retained in evidence/install-update-hosted-failure-836a0a7.log. A regression executes the harness and verifies its full-check/idempotence/rollback behavior.
