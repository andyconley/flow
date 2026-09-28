# Validation Plan

- Run `test_flow.py` in the clean pinned worker.
- Prove invalid Shaper intent is rejected during `approve-definition` without state/history mutation.
- Prove incomplete Delivery Lead plans and unsupported protocol-v8 limits are rejected before implementation or dispatch.
- Prove valid review-only amendments, immutable originals, constrained deltas, atomic failure, replay/conflict handling, unsafe-path and symlink rejection, tamper detection, compatibility, effective review resolution, and digest-bound acceptance dispositions.
- Require independent verifier evidence before handback.
