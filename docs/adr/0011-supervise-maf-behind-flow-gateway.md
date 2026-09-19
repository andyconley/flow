# ADR 0011: Supervise MAF behind a Flow-owned execution gateway

- Status: accepted design direction
- Date: 2026-09-19

## Context

Flow will adopt Microsoft Agent Framework/Magentic as a replaceable Delivery Lead execution runtime. Flow already owns a Python CLI, project run lifecycle, orchestration manifest, and evidence gates. The MAF spikes showed useful coordination and checkpoint behavior, plus replay, cost, provenance, and bypass risks. Andy confirmed that the exercise is to show the adoption path and its issues, then accepted the supervised-runner packaging option. Production integration is not yet implemented.

## Decision

Introduce one Flow-owned execution gateway for launch, policy decisions, action identity, approvals, receipts, and reconciliation. Run MAF in an optional, separately supervised local process. The Flow CLI initiates an attempt against an existing run; MAF requests specialist work and replans through the gateway. Only Flow grants dispatch and advances lifecycle state. A later MCP surface calls the same Flow application gateway. Keep MAF payloads and checkpoints outside Flow's domain schemas, linked by stable IDs.

## Consequences

- The core Flow CLI can operate without MAF or provider SDKs installed.
- Worker crashes have an explicit process boundary, but Flow needs a small versioned local protocol and supervision logic.
- Two state stores require durable IDs, checkpoint links, idempotent replay handling, and `unknown` reconciliation.
- Paid adapters stay disabled until enforceable budget limits and usage evidence exist.
- A single guarded construction path and independent receipt observer are required for production handback.
- The runtime can later be replaced without migrating Flow's lifecycle, charter, and evidence record.

## Alternatives considered

- **Optional in-process MAF import:** simpler calls and debugging, but MAF/provider failures and dependencies affect the CLI process and obscure crash supervision.
- **MAF fork or manager-owned policy:** richer control over internals, but increases upgrade coupling and cannot make Flow authority universal if other construction paths remain open.
- **Flow-native engine:** would duplicate planning, scheduling, and checkpoint mechanics that MAF is intended to supply; retained only as a contingency if a required capability cannot be integrated safely.

## Follow-up

Shape the foundation and execution-contract slice in `flow-plan`. The [adoption design](../maf-adoption-design.md) lists the remaining integration issues and acceptance evidence. This ADR selects architecture direction; it does not enable MAF in production or authorize a paid provider call.
