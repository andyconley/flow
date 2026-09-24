# Solution: adopt MAF beneath Flow

- Status: recommended architecture accepted by Andy on 2026-09-19. This approves the design direction, not production runtime enablement.
- Confirmed scope: Andy corrected the prior pass/fail framing to an exercise showing how Flow will adopt MAF and what issues the integration raises; “Proceed” confirmed that scope.
- Durable design: [docs/maf-adoption-design.md](../../../docs/maf-adoption-design.md).
- Archive retrieval selection: `1c7eb30561d5c7502599bee95d9e03fcbf1d83661d6c34dce7a195d5d260d5c6`. Four results were returned, none a directly applicable MAF execution decision. The four MAF spike runs were inspected manually outside that selection.

## Options and recommendation

A. **Flow-owned gateway around public MAF workflow APIs**: Flow issues grants and owns records; MAF plans and coordinates; guarded executors call providers. This is the recommended, reversible integration. It preserves Flow's domain model and makes MAF replaceable, at the cost of a reconciliation boundary.

B. **Embed policy in a custom Magentic manager or fork MAF**: Richer internal scheduling access, but raw participants and alternate builders can bypass manager-only controls; a fork increases upgrade cost and couples Flow state to MAF internals. Keep this as a narrow fallback if public APIs cannot carry required identity or resume behavior.

The user has chosen MAF adoption as the design premise, so a Flow-native execution engine is not being recommended. The gateway follows `scaffolds/default/standards/architecture.md` Layering and Domain/integration boundaries, `scaffolds/default/standards/orchestration.md` Required artifact and Claim provenance, and `docs/architecture.md` Project Overlay and Source-of-Truth Rule.

Andy accepted the **supervised local MAF runner** packaging option on 2026-09-19. Flow's CLI supervises it and remains the sole policy and lifecycle authority. An in-process MAF package was considered for a shorter call path but would couple CLI availability and crash recovery to MAF/provider dependencies. The decision is recorded in [ADR 0011](../../../docs/adr/0011-supervise-maf-behind-flow-gateway.md).

## State and rollout

Flow owns charter, lifecycle, grants, hard caps, evidence and receipt. MAF owns replaceable orchestration and checkpoints. The first launch surface should be the existing Flow CLI/run lifecycle; MCP should expose the same Flow gateway to ChatGPT/Claude rather than start a second execution path. Five independent slices in the design cover contracts, local guarded workflow, recovery, provider adapters and cost, then Shaper approvals and operational handback.

## Risks and owners

- Replay and split-state reconciliation: Flow state/runtime owner; test crash points and durable IDs before provider expansion.
- Unmetered paid work: provider adapter owner; fail closed until enforceable cap and usage observation.
- Bypass via raw MAF construction: Flow runtime owner; one gateway and tests for every entry point.
- Receipt provenance and Git binding: evidence owner; seal outside worker scope and verify independently.
- MAF upgrade/checkpoint compatibility: runtime owner; pinned versions and resume migration rehearsal.

## Session model advice

Coordinator: judgment, provisionally mapped to `gpt-5.6-sol` at high effort for cross-boundary architecture. Active parent identity: unknown (no verified same-session evidence). Effective delegated assignment: solution-architect uses its configured model. Switch performed: no.

## Next lane

`flow-plan`: shape the foundation/contract slice. This solution artifact does not implement or approve production MAF integration.
