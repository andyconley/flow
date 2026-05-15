# Solutioning Decisions

This standard defines the criteria for choosing among options during solutioning and for ending the activity.

## Decision criteria

These must be answered (yes/no, or documented exception) before solutioning is done.

### Architectural fit

- Solution stays within the correct layer(s) per `architecture.md`.
- Respects existing boundaries — no new cross-service DB access, no breaking of established multi-tenant, runtime, or domain patterns.
- Reuses existing patterns from `patterns.md` where possible (events, contracts, workflow steps).
- Any new architectural exceptions are explicitly called out.

### Risk and complexity reduction

- Story can be estimated within a known range or T-shirt size.
- Primary technical risks identified, owned, and mitigated — or explicitly accepted with rationale.
- No hidden dependencies on unproven tech or teams.

### Feasibility and constraints

- Implementable with current platforms and tools.
- Meets non-functional constraints (latency, throughput, safety, regulatory).
- No show-stopper dependency; if any exists, documented with options.

### Testability and observability viability

- Clear test strategy across the right layers per `testing.md`.
- Observability plan defined (logs, metrics, traces) per `observability.md`.
- Outcome instrumentation defined for measurable Success criteria.
- No reliance on untestable components or non-deterministic behavior without an eval strategy.

### Impact, scope, and cost

- Scope minimized — no unnecessary new services, topics, or behaviors.
- Affected components clearly listed (services, topics, schemas, edge nodes if relevant).
- Implementation effort and operational impact proportionate to value.

### Option comparison and rationale

- At least two viable options considered and recorded.
- Recommended option is clearly superior along dimensions that matter (simplicity, safety, reusability, time-to-value).
- Tradeoffs and explicit non-goals documented.

## Definition of "solutioning done"

- All decision criteria above answered (yes/no, or documented exceptions).
- Short proposed solution documented (diagram + description).
- Implementation work broken into INVEST-compliant chunks for `flow-plan` to shape.
- Follow-up spikes or open questions listed.
- Risks have owners and mitigations (see `solutioning-risks.md`).
- Suggested design artifacts named (e.g., spike Form A/B, ADR, contract specs, diagrams).

### Done vs Rejected

"Not pursuing" is a legitimate solutioning outcome. A solutioning activity that concludes the work shouldn't be done resolves as **Rejected** rather than Done; capture the reasoning in the closure summary. Don't force-close a Rejected solutioning as Done — the distinction matters for future searches and for institutional memory of what was considered.

## Relevant principle

Decisions are the durable output of solutioning. Each decision should leave behind enough rationale (rule citations, options considered, owner, expected impact) that future engineers can follow the trail. Solutioning that doesn't produce captured decisions has been wasted.

## Related standards

- `architecture.md` — the architectural rules the solution must respect; ADR convention.
- `patterns.md` — the pattern vocabulary the solution can draw from.
- `solutioning-criteria.md` — Success / Acceptance / DoD criteria types.
- `solutioning-risks.md` — risk, dependency, and blocker management.
