# Assignment Brief: Implementation

- Role: lead developer and serialized publication owner
- Provider: `/root`
- Task: implement the approved four-stage release validation gate, its contracts, tests, ADR, documentation, validation evidence, commits, and approved full-release sequence.
- Evidence inventory: `.github/workflows/release.yml` is the current one-job publisher; `release.config.cjs` owns current release rules; `install.sh`, `install-flow.sh`, `cli/`, and `tests/test_flow.py` contain existing install/update/runtime validation surfaces; the approved run artifacts define all requirements and exclusions.
- Search method: inspect the named files and use `rg --files` plus targeted `rg` queries before concluding a surface is absent.
- Write scope: `.github`, `release.config.cjs`, `scripts`, `tests`, `docs`, and this run's artifacts. Do not touch the canonical checkout's `docs/backlog.md`.
- Shared mutation: only this assignment may push or publish. Refresh remote/tag/release baseline immediately before a write, stop on drift, never force or bypass, and record execution, readback, and comparison evidence.
- Success: every acceptance criterion is implemented and validated, review findings are resolved, commits are conventional, and publication is proven or explicitly stopped before mutation.

