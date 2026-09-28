# Validation Plan

## Focused automated proof

- Valid same-state review amendment and immutable original evidence.
- Rejection in every other lifecycle state and for revision-1/legacy runs.
- Exact replay idempotency; stale, conflicting, and repeated-amendment refusal.
- Content-addressed path, symlink, traversal, malformed schema, and byte-tamper refusal.
- Delta allowlist enforcement for verification corrections and appended read-only reviewers.
- Required, non-deferred AC2/AC13 dispositions bound to original acceptance criteria.
- Effective manifest used at dispatch and acceptance; original authority retained for Delivery evidence.
- Acceptance event binds amendment, replacement, and disposition digests.
- Existing lifecycle and orchestration regression suites remain green.

## Real-run proof

- Reproduce the current acceptance failure before amendment.
- Approve exactly one constrained amendment for `maf-runtime-readiness-2`.
- Validate dispatch before each fresh reviewer.
- Obtain fresh quality, test, security, and SRE evidence against final HEAD.
- Run acceptance validation and `accept-review`; archive only after both succeed.

## Documentation proof

- Review ADR/runtime-address wording, installation-time location, unsupported-host activation state, and bug-planning prerequisite against implemented behavior.

