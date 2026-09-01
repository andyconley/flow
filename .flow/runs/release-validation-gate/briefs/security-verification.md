# Assignment Brief: Security Verification

- Role: independent security and acceptance verifier
- Provider: `/root/release_gate_security`
- Task: independently verify the write-token boundary, least privilege, artifact integrity, shell injection resistance, exact-SHA binding, serialized publisher ownership, and repair-forward safeguards.
- Evidence inventory: `.github/workflows/release.yml` currently grants workflow-wide write permissions; `release.config.cjs` configures changelog, Git, and GitHub publication; the approved plan and validation plan define the intended boundary; implementation evidence will enumerate changed paths and commands.
- Search method: inspect the full workflow, configuration, helper scripts, tests, run artifacts, and diff; use targeted searches for tokens, shell interpolation, force operations, bypasses, and failure-tolerant controls.
- Constraint: distinct provider, read-only repository review, no evidence collection on behalf of the producer; record the verdict in `review/security-review.md`.

