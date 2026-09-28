# Plan: Review Provenance Refinement

## Outcome

Enable one constrained, auditable correction for a provenance-blocked reviewing run without rewriting original Delivery authority, then use it to complete the MAF review.

## Slices

1. Add `approve-review-amendment` as `reviewing -> reviewing`; define content-addressed replacement, disposition, and digest-chained amendment records with atomic/idempotent failure behavior.
2. Add an effective-review-manifest resolver and strict delta allowlist. Review dispatch and acceptance use the overlay; Delivery history stays bound to the original.
3. Add lifecycle, CLI, tamper, unsafe-path, replay/conflict, acceptance-binding, and compatibility tests.
4. Apply one amendment to `maf-runtime-readiness-2`, record AC2/AC13 dispositions, correct the bounded ADR/support/planning guidance, dispatch four fresh independent reviews, then validate, accept, and archive if green.

## Boundaries

No general artifact editing, multiple amendment generations, non-review amendment states, macOS baseline repair, MAF redesign, or direct `<new> -> planning` shortcut.

