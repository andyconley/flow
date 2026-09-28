# Implementation Handoff

The Codex Delivery Lead must use `job-charter.json` through `execute-chartered-job` in a clean isolated worktree pinned to the approved source commit. The Claude producer may edit only `cli`, `tests`, `docs`, `scaffolds`, and `README.md`; the local verifier is read-only. No manual implementation agent substitutes for a failed gateway.

Original manifests and approved digests are immutable. Failed lifecycle or amendment validation writes no state/history. The coordinator—not the worker—will later apply the new amendment mechanism to `maf-runtime-readiness-2`.
