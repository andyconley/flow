## Archive Summary

### Work Closed

- `agent-expertise-advisory-mac-release` was accepted on 2026-09-25 (`review.md`, final acceptance) and shipped in v0.29.0.
- It adds personal active-Mac advisory expertise for architect, business-analyst, lead-developer, sre, support-lead, and test-engineer in generated Flow coordinators (Claude and Codex): `flow expertise brief`, `disposition --handback-stdin`, and `feedback`, plus an overlay rollback switch.

### Validation

- 1,095 tests passed with one skip, release run `34901200322` passed, post-release client checks were run, and the feature has been live in coordinators since release.

### Residual Risks

- `brief` trusts the caps its outcome reports.
- The feedback lane is whatever the caller says.
- `receipts inspect` hides pre-only receipts.
- Non-exercised lanes and sandbox profiles are unqualified.

### Follow-up Work

- Broader five-environment qualification (deferred).
- Harden `brief`'s size and cap recomputation.

### Capability Gaps Observed

- Not assessed; archived retroactively during housekeeping.
