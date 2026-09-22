# Research note: current boundary and reuse

## Observed

- `docs/maf-adoption-design.md` assigns Flow lifecycle, policy, grants, evidence, receipts, and recovery; MAF/Magentic coordinates execution.
- The current code contains versioned execution contracts, a ledger, a Flow-owned gateway, supervised Magentic execution, provider adapters, receipt validation, and chartered-job tests.
- Flow already has 13 canonical specialist definitions and an orchestration manifest standard.
- ChatGPT Work, Claude Code, and Codex can all work against local Flow artifacts, but no formal cross-runtime continuation contract currently makes those artifacts the explicit handoff boundary.
- Archive search returned `identity_unavailable` because `.flow/identity.json` is absent in this clean worktree. No archive claim was treated as evidence.

## Inferred

- The smallest coherent enhancement is a contract and ownership transition layered over the existing control plane.
- Cross-runtime continuation can be artifact-based; direct transfer of model session state is neither necessary nor a safe authority mechanism.

## Recommended

- Add versioned Shaper and Delivery Charter schemas, an explicit transition event, and runtime adapters that read the same canonical Flow state.
- Generalize the current launcher only after the charter/transition contract is settled.
- Keep ordinary Chat MCP ingress deferred and independently threat-modeled.

## Model context

The Flow model advisor recommended the judgment profile, provisionally mapped to `gpt-5.6-sol` at high effort. Availability and active same-session model identity were unverified; no switch was performed.
