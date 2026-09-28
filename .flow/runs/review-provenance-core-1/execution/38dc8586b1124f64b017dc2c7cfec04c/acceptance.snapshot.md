# Acceptance Criteria

1. Add an explicit review-only amendment transition that never rewrites the original approved orchestration manifest or its digest.
2. Permit only verification corrections and appended read-only review assignments; reject broader path, provider, role, capability, producer, or authority expansion.
3. Record immutable amendment lineage and resolve the effective review manifest deterministically for review dispatch and acceptance.
4. Reject replay conflicts, tampering, unsafe paths, symlinks, and invalid deltas atomically with unchanged state/history.
5. Preserve compatibility for runs without amendments and bind acceptance dispositions to the effective review evidence.
6. `approve-definition` validates canonical Shaper intent before lifecycle writes; invalid intent leaves state/history unchanged.
7. Guidance distinguishes direct/manual orchestration from a chartered Delivery Lead job.
8. Approval or dispatch rejects a Delivery Lead plan lacking a manager, provider/model bindings, bounded editable producer, independent read-only verifier, linked charter, safe targeted test, or isolated pinned worktree contract.
9. Approval rejects protocol-v8 runtime or Magentic ceilings above supported limits.
10. Focused lifecycle, CLI, orchestration, compatibility, replay/conflict, unsafe-path, tamper, and predecessor-regression tests pass in the clean worker.
