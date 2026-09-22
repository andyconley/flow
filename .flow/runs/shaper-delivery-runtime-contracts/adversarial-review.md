# Adversarial review

Status: proposed findings; no requirements approved.

| Challenge | Consequence | Required response |
| --- | --- | --- |
| Delivery Lead silently reinterprets an ambiguous outcome | Scope and acceptance drift | Immutable charter; halt and versioned amendment for material ambiguity |
| Chat or runtime transcript is treated as authoritative | Decisions cannot be reproduced or audited | Stable IDs, canonical artifacts/digests, explicit decision records |
| Work, Claude, and Codex each create their own run | Split evidence and conflicting approvals | Inspect-before-mutate continuation handshake; explicit fork event only |
| Magentic or a nested provider launches work outside Flow | Unbounded calls and missing provenance | Gateway-only construction and per-call grants; deny raw participants |
| Shaper research call mutates delivery state | Definition bypasses approval | Research-only grants, read/write scopes, evidence status, no delivery eligibility |
| Amendment overwrites an approved charter | Historical receipt becomes misleading | Append-only versions and transition/amendment lineage |
| Existing job records cannot parse new schemas | Adoption breaks accepted work | Additive schema versions, readers for old records, actionable fail-closed diagnostics |
| Provider identity changes on resume | Policy or credential confusion | Record capability/provider binding and reauthorize substitutions |
| Multiple Delivery Leads act concurrently | Duplicate sends and conflicting checkpoints | One active lead per attempt and durable supersede/resume event |
| Ordinary Chat tunnel is rushed into the critical path | New network and auth exposure delays core capability | Explicit non-goal; separate security definition later |

## Role review synthesis

- Business analysis: distinguish Definition authority from Delivery sequencing and make amendments explicit.
- Product review: stages 1-2 (contract plus transition) are the minimum useful slice; prove one real charter-driven job later.
- Architecture review: reuse the ledger, gateway, launcher, manifests, and receipts; keep MAF state subordinate and cross-runtime continuation artifact-based.
