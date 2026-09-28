# Requirements: Review Provenance Refinement

Flow rejects an incomplete sealed producer record but cannot approve a constrained review-stage correction without overwriting historical authority. Add one review-only, append-only, digest-bound amendment mechanism; preserve the original manifest and Delivery digests; bind explicit AC2 and AC13 dispositions; correct the bounded MAF ADR/support discrepancies; then use the mechanism for fresh independent review and gated acceptance of `maf-runtime-readiness-2`.

The amendment must fail closed outside protocol-revision-2 `reviewing`, for unsafe or authority-expanding changes, for tampering, and for stale or conflicting requests. General artifact editing, multiple amendment generations, macOS baseline repair, MAF redesign, and a direct new-run-to-planning shortcut are excluded.

