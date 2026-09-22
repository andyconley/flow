# Research note: current boundary and reuse

## Observed

- `docs/maf-adoption-design.md` assigns Flow lifecycle, policy, grants, evidence, receipts, and recovery; MAF/Magentic coordinates execution.
- The current code contains versioned execution contracts, a ledger, a Flow-owned gateway, supervised Magentic execution, provider adapters, receipt validation, and chartered-job tests.
- Flow already has 13 canonical specialist definitions and an orchestration manifest standard.
- ChatGPT Work, Claude Code, and Codex can all work against local Flow artifacts, but no formal cross-runtime continuation contract currently makes those artifacts the explicit handoff boundary.
- Archive search returned `identity_unavailable` because `.flow/identity.json` is absent in this clean worktree. No archive claim was treated as evidence.

Archive selection ID: `984d54939dffb82f0467afb3bb25ddf765529fdde608572abbfbe2043d793fca`. This unavailable result was the lane's single automatic archive search; later repository inspection was manual evidence outside that selection.

## Inferred

- The smallest coherent enhancement is a contract and ownership transition layered over the existing control plane.
- Cross-runtime continuation can be artifact-based; direct transfer of model session state is neither necessary nor a safe authority mechanism.

## Recommended

- Add versioned Shaper and Delivery Charter schemas, an explicit transition event, and runtime adapters that read the same canonical Flow state.
- Generalize the current launcher only after the charter/transition contract is settled.
- Keep ordinary Chat MCP ingress deferred and independently threat-modeled.

## Model context

The Flow model advisor recommended the judgment profile, provisionally mapped to `gpt-5.6-sol` at high effort. Availability and active same-session model identity were unverified; no switch was performed.

## Advisory expertise

- Business-analyst request: `fd00d29a-51f6-4e91-a4cb-da72db668c6e`.
- Delivered advice: leave requirements explicitly unresolved when evidence is thin.
- Disposition: applied. The Work adapter/locality acceptance is now conditional on a bounded feasibility probe, while the overall cross-runtime target remains explicit.
- Post-receipt digest: `87cbc0ddca3302614ea57911094aea6705b36607a715bd20790d496bde589fbf`.
