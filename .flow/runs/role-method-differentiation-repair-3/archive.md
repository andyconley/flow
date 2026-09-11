## Archive Summary

### Work Closed

- `role-method-differentiation-repair-3`
- Released the accepted expertise expansion as `v0.28.0`. Architect,
  lead-developer, and test-engineer now use their evidence-backed methods;
  product-manager and quality-reviewer remain base-only. The resulting composed
  cohort contains architect, business-analyst, lead-developer, SRE,
  support-lead, and test-engineer.
- Preserved the failed product-manager and quality-reviewer evidence and all 112
  protected historical files. Candidate production digest `T`
  (`4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`)
  matched source commit `C`
  (`efb73c85d07dc4c091b104f558fa281db0c540ad`). The change was
  fast-forwarded into `main`, published from release commit `R`
  (`6055b6b2dd4ca5fe9a9879d61523bbd08fa0736d`), installed, and checked
  through fresh Claude and Codex clients.

### Rationale

Only roles with evidence of marginal behavioral lift entered this release.
Architect, lead-developer, and test-engineer passed the accepted evidence gates;
product-manager and quality-reviewer did not. Keeping the unsuccessful evidence
preserves an auditable admission boundary while leaving new candidate methods
reversible and separately reviewable.

### Applies When

This outcome applies when Flow generates its default Claude and Codex agents for
architect, lead-developer, or test-engineer responsibilities. Product-manager
and quality-reviewer remain base-only until a separate approved evidence run
supports composition. Re-run the client matrix after relevant client, routing,
model, or entitlement changes.

### Work Type

Cross-runtime agent expertise composition and evidence-gated release.

### Mentions

Architect, lead-developer, test-engineer, product-manager, quality-reviewer,
expertise composition, evidence admission, Claude, Codex, and `v0.28.0`.

### Validation

- Automated: 49 focused tests and the 996-test full suite passed. The final
  frozen verifier passed 250 checks. Three negative mutations failed their
  intended guards, restored exact source bytes, and returned to a passing
  result. Help generation, diff checks, user and isolated adapter sync checks,
  runtime smoke, run verification, and normal and strict doctor checks produced
  the accepted results. Doctor reports zero errors and four accepted warnings.
- Manual: fresh Claude and Codex status invocations loaded the installed Flow
  skill and reported `v0.28.0`. Fresh test-engineer invocations produced the
  required row-7 and invalid-email oracle, including error visibility,
  non-persistence, correction, and successful retry. The generic support-lead
  smoke cells were superseded by this approved, change-relevant matrix; no
  support-lead live result is claimed.
- Runtime/deploy: release workflow `34515517662` completed its analyze,
  validate-candidate, publish, and verify-published jobs successfully. The
  public tag and release resolve to `R`; `~/.flow/source` resolves to the
  released checkout; installed and isolated Claude and Codex adapters matched
  byte for byte; and post-release native checks passed.

### Residual Risks

- `flow doctor` continues to report the accepted warning set:
  `user.claude.runtime_smoke`, `user.codex.runtime_smoke`,
  `project.adoption.runtime_surfaces`, and `telemetry.plugin_usage`. The live
  client checks required by this release were completed separately.
- Client upgrades, model-routing changes, or account-entitlement changes can
  invalidate the runtime evidence and require a fresh matrix.
- Product-manager and quality-reviewer remain base-only. A general admission
  policy or new candidate methods require their own approved work and evidence.

### Follow-up Work

- Re-run authenticated client and routing evidence when client versions, model
  mappings, or account entitlement changes.
- Define the deferred two-axis expertise-admission policy or new
  product-manager and quality-reviewer candidate screens only when a named
  workflow need justifies them.
- Consider promoting `promoted-gap-frequency-staleness`; it is now a repeated
  open gap. The other repeated gaps below are already promoted.
- No implementation, merge, release, or installation work remains for this
  run.

### Capability Gaps Observed

- Flow still lacks an explicit review-to-implementation transition for required
  corrections, so this evidence repair required a separate successor run.
- Flow still lacks a single delivery completion manifest binding reviewed
  source, release identity, regenerated adapters, diagnostics, and fresh
  cross-runtime results; the delivery receipts were assembled manually.
- Flow still lacks a managed durable memory write contract for Codex archive
  closeout.
- Flow does not refresh observation counts in promoted backlog entries when the
  capability-gap ledger records later repeats, leaving central priority
  signals stale.
- Ledger: reused `review-rework-transition`,
  `runtime-evidence-completion-manifest`,
  `runtime-memory-capability-contract`, and
  `promoted-gap-frequency-staleness` for this run. No new key was created.
- Repeats: `review-rework-transition` is now seen 6 times;
  `runtime-evidence-completion-manifest` 5 times;
  `runtime-memory-capability-contract` 5 times; and
  `promoted-gap-frequency-staleness` 2 times. The first three are already
  promoted; the last remains open.

### Memory Updates

- STATE (`.flow/memory/STATE.md`): recorded the `v0.28.0` completion, removed
  the completed expertise-release and live-client actions, and kept current
  deferred work visible.
- Runtime memory entries written: n/a — no durable provider.
- Parent-overlay implications: none.
