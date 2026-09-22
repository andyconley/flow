# Definition: Shaper and Delivery Lead runtime contracts

- Work item: `shaper-delivery-runtime-contracts`
- Definition lead: Codex coordinator with Flow role review
- Opening role: solution-architect
- Status: Draft — not approved
- Approver: Andy Conley

## Problem or opportunity

Flow has a supervised, Flow-gated Magentic delivery path, but it does not yet have one explicit runtime-neutral contract for shaping work, sealing a delivery charter, transferring ownership, and continuing the same run from ChatGPT Work, Claude Code, or Codex. Without that contract, runtime sessions can become accidental sources of truth and the Delivery Lead can appear to own decisions that belong to Definition.

## Desired outcome

A Shaper can define and, when necessary, solution work from any supported surface. Explicit approval seals an immutable Delivery Charter and transfers operational ownership to one Delivery Lead for a delivery attempt. The Delivery Lead plans and executes within the charter through Flow-authorized Magentic specialist calls. Flow remains the durable authority for lifecycle, policy, artifacts, eligibility, approvals, evidence, recovery, and handback.

## Scope

1. A runtime-neutral Shaper contract spanning `flow-define` and optional `flow-solution`.
2. A versioned Delivery Charter derived from approved Definition artifacts.
3. An explicit Definition-to-Delivery ownership transition and amendment path.
4. A Delivery Lead contract spanning `flow-plan`, `flow-implement`, `flow-review`, and `flow-archive`.
5. Artifact-based continuation among ChatGPT Work, Claude Code, and Codex.
6. Generalization of the existing Flow gateway and launcher so Magentic coordinates only the charter's eligible Flow specialists.
7. Compatibility and migration rules for existing chartered execution records.

## Non-goals

- Ordinary Chat MCP ingress, a secure tunnel, or local Chat connectivity.
- A second Flow lifecycle kernel, DAG engine, scheduler, or checkpoint system.
- MAF ownership of charter, policy, approval, evidence, or acceptance.
- Transfer of proprietary chat/session state between runtimes.
- Unrestricted nested provider subagents.
- A reliable dollar stop or new token accounting system.

## Source evidence

- `docs/maf-adoption-design.md`: accepted Flow/MAF authority boundary and adoption direction.
- `.flow/PROJECT.md`: Flow is runtime-neutral and uses approved run artifacts as sources of truth.
- `scaffolds/default/standards/orchestration.md`: manifest, provenance, risk, and verification rules.
- `scaffolds/default/standards/evidence.md`: evidence qualification and artifact integrity.
- Current `cli/execution_contracts.py`, `cli/delivery_gateway.py`, and chartered gateway tests: an existing control plane, ledger, grants, roster, receipts, and recovery to extend rather than replace.
- Archive retrieval was unavailable because this clean worktree has no `.flow/identity.json`; repository evidence was inspected directly and this limitation remains explicit.

## Requirements and acceptance

See `requirements.md` and `acceptance-criteria.md`.

### Success criteria

- Shaping intent and delivery authority remain understandable and auditable when operators change runtimes.
- The Delivery Lead can coordinate useful work without gaining authority to reshape the approved outcome.
- Existing Flow lifecycle, policy, evidence, and recovery machinery remains the single control plane.

### Constraints

- Preserve append-only approved artifacts and compatibility with existing chartered execution records.
- Use only Flow-enforceable controls; record usage observations without claiming unavailable dollar or token enforcement.
- Keep MAF/Magentic and provider session state subordinate to Flow artifacts and identifiers.

### Assumptions

- ChatGPT Work, Claude Code, and Codex can each access the relevant Flow project artifacts through a supported local adapter; the exact Work adapter and locality rules remain unverified.
- One active Delivery Lead per attempt is sufficient for the first contract version.
- Existing specialist definitions and the chartered gateway are suitable extension points rather than replacement targets.

## Research implications

- Current authority boundary is already aligned -> extend the gateway and launcher; do not build a second kernel.
- Existing execution schemas are job-specific -> define a compatibility-preserving charter version and migration path.
- Cross-runtime session transfer is neither necessary nor trustworthy -> continuation uses stable Flow IDs, digests, artifacts, and receipts.
- Shaper research may benefit from Magentic -> permit only separately granted, evidence-producing research calls; they cannot approve or execute delivery.

## Adversarial review

See `adversarial-review.md`. Material risks are silent charter drift, duplicate policy paths, session identity confusion, nested-call bypass, and incompatible migration.

## Proposed staged roadmap

1. Contract schemas and CLI inspection.
2. Sealed Delivery Charter and Definition-to-Delivery transition.
3. Generalized charter intake through the existing Flow-gated Magentic launcher.
4. Artifact-based continuation in ChatGPT Work, Claude Code, and Codex.
5. One bounded charter-driven delivery proof with independent verification.
6. Governed amendments and delegated Shaper approvals.
7. Optional ordinary Chat read/state ingress after the core path is accepted.

## Open decisions before approval

- Final schema names, versioning, canonical encoding, and digest algorithm.
- Whether an amendment creates a new charter version, linked delivery epoch, or both.
- Initial Work adapter packaging and operator identity binding.
- The evidence and supported locality needed to prove ChatGPT Work can open the same canonical project/run on a given machine.
- Initial specialist/provider eligibility and nested-subagent policy.
- Which expansion decisions a Shaper may approve automatically, including expiry and revocation.
- Whether Magentic needs an upstream extension for durable action metadata.

## Next lane

- Further definition and explicit engineer approval.
- After approval, use `flow-solution` because schema, compatibility, amendment, and adapter choices remain architectural.
