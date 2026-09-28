# Validation Plan

- Targeted gateway proof: `test_flow.py` on a clean pinned worker.
- Regression tests: invalid Shaper intent rejected during `approve-definition`; incomplete Delivery Lead plan and unsupported protocol-v8 limits rejected before implementation/dispatch; invalid Claude manager turn-count shape handled before unrecoverable reconciliation while unknown sends remain fenced.
- Amendment tests: valid review-only event; immutable original; constrained deltas; atomic failure; replay/conflict; unsafe paths/symlinks; tampering; compatibility; effective dispatch and acceptance; digest-bound dispositions.
- Independent verifier evidence from the chartered job, followed by Flow test, quality, security, and SRE review.
- Real-run proof: gated amendment of `maf-runtime-readiness-2`, four fresh final-HEAD reviews, acceptance validation, acceptance, and archive.
