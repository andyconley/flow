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
| Approval or transition is replayed | Duplicate Delivery Charters or active attempts | Idempotent transition and explicit withdrawal/cancellation semantics |
| Two runtimes mutate the same run or use a nonportable local path | Lost updates or wrong-worktree execution | Serialized lifecycle mutation and verified local binding |
| Delivery Lead crashes while still considered active | Permanent block or concurrent replacement | Durable lease identity with explicit expiry/resume/supersede rules |
| Multiple Delivery Leads act concurrently | Duplicate sends and conflicting checkpoints | One active lead per attempt and durable supersede/resume event |
| A partially migrated legacy record passes shallow validation | Dispatch under corrupted authority | Compatibility validation includes schema completeness and digest integrity |
| Ordinary Chat tunnel is rushed into the critical path | New network and auth exposure delays core capability | Explicit non-goal; separate security definition later |

## Role review synthesis

- Business analysis: distinguish Definition authority from Delivery sequencing and make amendments explicit.
- Product review: stages 1-2 (contract plus transition) are the minimum useful slice; prove one real charter-driven job later.
- Architecture review: reuse the ledger, gateway, launcher, manifests, and receipts; keep MAF state subordinate and cross-runtime continuation artifact-based.
- Advisory expertise: retain the Work adapter/locality rule as unresolved until a bounded feasibility probe supplies the missing evidence.
