# Adopting Microsoft Agent Framework beneath Flow

Status: architecture direction accepted 2026-09-19; production integration remains future work. Andy's direction is to show **how** Flow adopts MAF and what issues that creates. He accepted a supervised local MAF runner behind the Flow gateway. The four completed spikes are research evidence; they are not production integration. This document supersedes their earlier pass/fail framing, while preserving their observations.

## Target boundary

```mermaid
flowchart TD
    U[Andy] --> S[Shaper: charter and bounded approvals]
    S --> F[Flow: lifecycle, policy, system of record]
    F --> G[Flow execution gateway]
    G --> M[MAF/Magentic: Delivery Lead execution]
    M --> G
    G --> W[Flow specialists: Codex, Claude, local]
    W --> G
    G --> F
```

Flow accepts a versioned charter and approved orchestration manifest, creates a run and execution attempt, and passes an immutable execution envelope to MAF. MAF plans, selects specialists, coordinates parallel work and handoffs, and checkpoints its execution. Every proposed delegation, replan, budget expansion, or consequential approval returns through a Flow gateway **before** a worker call. Flow records the decision and issues a scoped dispatch grant. A Flow-owned adapter turns that grant and the existing specialist definition into a Codex SDK/App Server, Claude Agent/Code, or local inference call. Worker results return to Flow as evidence and a receipt; MAF receives only the normalized result it needs to continue. Shaper can approve permitted expansion under the charter; anything outside delegated authority escalates to Andy.

MAF's checkpoint is execution state. Flow's run, manifest, charter version, policy decisions, receipt, artifact hashes, and reconciliation state remain authoritative. A checkpoint cannot authorize a new call merely because it contains a queued message. Flow can change the runtime behind the execution gateway without migrating the project record into MAF's models.

The first production launch should attach to an existing Flow CLI run. A separately supervised local MAF runner is the preferred packaging shape: Flow's current CLI remains usable without MAF installed, and a crashed worker process has an explicit recovery boundary. The runner exchanges versioned action and event records with Flow through a narrow local protocol; it cannot issue its own grants. An in-process optional MAF package is a simpler fallback for an initial constrained slice, but would couple the CLI process to MAF and provider failures. Neither launch surface exists in production today. MCP should later call the same Flow application gateway from ChatGPT or Claude, rather than create a second policy path.

## Integration contract

| Boundary | Flow-owned input or output | MAF's job |
| --- | --- | --- |
| Start | `run_id`, `attempt_id`, charter digest, manifest digest, allowed specialist definitions, budget and limits, approval matrix | Build the workflow from guarded participants and start or resume it |
| Proposed action | Stable action ID, kind, role, provider, requested cost cap, concurrency slot, scope and parent action | Propose a delegation or replan; wait for grant or denial |
| Grant | Policy decision ID, one-use dispatch token, scope, expiry, charter version | Route the authorized call to the selected participant |
| Result | Provider/session identity, observed usage, output/artifact hashes, validation evidence, status (`completed`, `failed`, `unknown`) | Incorporate normalized result into its plan and handoffs |
| Resume | Flow attempt and reconciliation state, MAF checkpoint identity and version | Restore execution state; re-submit pending actions to Flow for idempotent resolution |
| Handback | Flow-sealed execution receipt, artifact provenance and validation, unresolved risks | Supply trace and final synthesis; never declare Flow acceptance itself |

The gateway is the sole production construction path for MAF participants. It accepts Flow specialist specs, constructs guarded executors, and denies raw Agent/Executor injection. Flow's deterministic gate owns the six-delegation, three-concurrent, two-replan, allowlist, paid-budget and expansion rules. MAF's round/reset limits remain useful safety bounds, not policy authority. Paid adapters need an enforceable per-call cap and independently recorded usage; the prior Codex subscription path did not supply a reliable dollar stop, so it stays blocked until a valid cap or a separately approved accounting rule exists.

Action IDs bind the run, charter version, specialist definition and instance, and a durable invocation sequence. Flow stores action intent and grant before dispatch. After a crash, a replay of the same action ID returns its prior status; `unknown` requires reconciliation before retry. A new action ID is allowed only for a genuinely new authorized call. Replan IDs must survive manager restart, not depend on an in-memory counter. Receipt evidence should be sealed outside worker write scope and linked to Git commit/tree identity when code changes are involved.

## Adoption sequence

1. **Foundation and contract.** Add Flow-owned charter/envelope, action ID, grant, execution receipt, and checkpoint-reference schemas. Persist them under the project overlay's run artifacts with migration-ready storage boundaries. Add an ADR for Flow/MAF state ownership and runner packaging. Acceptance: schema round trips and deterministic policy tests run without MAF installed.
2. **Guarded local vertical slice.** Package MAF as an optional, supervised local execution runtime. Add a Flow CLI launch path and make its gateway the only participant construction path; load one existing specialist definition and run one local worker under the six/three/two envelope. Acceptance: a raw participant cannot enter through Flow; an unauthorized proposed action makes zero worker calls; receipt links charter, definition, decision, checkpoint and result.
3. **Multi-turn and recovery.** Persist invocation/replan identity across process restart, execute two authorized calls, interrupt during a third, and reconcile `unknown` before any retry. Acceptance: replay never creates an extra provider call or an untracked continuation; a third replan is denied by Flow.
4. **Provider adapters and cost.** Add thin Codex, Claude and local adapters behind the same grant/result contract. Start with local execution; enable each paid path only after its cost limit and usage evidence are enforceable. Acceptance: mixed workflow returns comparable receipts, preserves the 13 definitions and producer/verifier separation, and stops at the approved budget.
5. **Shaper approval and operational handback.** Route proposed expansion to delegated Shaper approval or Andy according to the charter. Add trace correlation, cancellation, stuck-run recovery, receipt verification, operator diagnostics, and MCP ingress over the same gateway. Acceptance: approvals cannot bypass Flow policy; a restarted run and an independently checked code artifact produce a trustworthy handback through CLI and MCP.

Each slice should be independently reviewable. Keep the freeze on building a Flow-native DAG engine, scheduler, and checkpoint system while MAF supplies those mechanics. Measure the expected machinery reduction by comparing the actual Flow integration code and ongoing operations with a scoped native-runner estimate; treat “70%” as a target to measure, not a gate for starting adoption.

## Issues to solve

| Issue and evidence | Integration response | Owner / proof |
| --- | --- | --- |
| Runtime-originated Magentic calls can bypass a gate if participants are built directly. The interruption spike guarded one factory only. | Make Flow's gateway the only application entry point; test every workflow constructor and plugin path. | Flow runtime owner; unauthorized-call test at each entry point. |
| MAF custom participant requests do not carry a durable invocation ID. The multi-turn spike used checkpointed workflow state; a fresh manager continued after a denied replay until the participant was changed to halt. | Persist Flow action intent and sequence; halt on duplicate or `unknown`; make manager continuation contingent on reconciliation. | Flow state owner; separate-process restart and replay test. |
| Replan identity in the latest probe is manager-local. | Assign replan IDs from Flow's durable attempt state before MAF replans. | Flow state owner; restart before and after second replan. |
| MAF and Flow have separate checkpoint/ledger states. The live interruption spike marked a streamed call `unknown`. | Link checkpoint to Flow attempt and last committed decision; define a recovery matrix for queued, started, completed, and unknown work. | Runtime owner; kill/restart tests at each boundary. |
| The first mixed-provider spike exceeded its intended $10 stop because subscription-backed Codex lacked a reliable dollar cap. Later gates blocked paid work. | Fail closed for unmetered paid providers; implement and verify per-provider budget enforcement before enablement. | Provider adapter owner; cap-exhaustion test with no extra call. |
| A stub receipt once labeled work as Ollama despite no physical provider call; review corrected it to `local-stub`. | Distinguish proposed, authorized, dispatched, observed, and stubbed work in the receipt; independently observe artifacts and usage. | Evidence owner; provenance review and negative test. |
| The 13 specialist definitions and mixed-provider handoff are only partly proven; prior live mixed work did not establish all role/artifact contracts. | Load definitions by digest, create unique instances, pass the same charter and artifact contract, and preserve producer/verifier separation. | Specialist owner; mixed-workflow integration test. |
| MAF version and checkpoint format are external dependencies. | Pin tested versions, keep MAF objects out of Flow's domain schemas, and exercise upgrade/resume compatibility. | Runtime owner; version migration and rollback rehearsal. |
| Shaper delegated expansion is designed but not exercised through MAF. | Represent approval as a Flow policy decision with scope, expiry and audit event; MAF waits for the decision. | Policy owner; allowed and escalated expansion tests. |

## Evidence and decision posture

The first spike demonstrated MAF fan-out and found separate core/orchestration version series, but much of its provider work was stubbed. The control-recovery spike demonstrated a Flow SQLite gate and live local Ollama execution. The Magentic interruption spike observed an actual streamed local call, intentional process exit and fail-closed replay in a separate process. The multi-turn spike proved distinct IDs, duplicate halt and a third-replan denial with deterministic `local-stub` responses in one process. Those are narrow observations, not proof that the production gateway, paid adapters or full recovery matrix already exist.

This design chooses **Flow-owned gateway around MAF** over embedding Flow policy in a custom Magentic manager alone. The manager can request and sequence work; the guarded participant and Flow ledger enforce it. A deeper fork of MAF could expose richer invocation metadata, but it would couple Flow to MAF internals and complicate upgrades. We will first integrate through public builder, executor, checkpoint and event interfaces, documenting any gap that requires an upstream change.

Relevant standards: `scaffolds/default/standards/architecture.md` (**Layering**, **Domain and integration boundaries**, **ADR convention**) keeps MAF behind adapters and Flow rules testable without it. `scaffolds/default/standards/orchestration.md` (**Required artifact**, **Claim provenance and reconciliation**, **Lifecycle enforcement**) requires a manifest, qualified evidence and stage gates; structural validation alone cannot prove runtime behavior. `docs/architecture.md` (**Project Overlay**, **Source-of-Truth Rule**) keeps project runs canonical and installed framework content separate. The archive search for “MAF Magentic execution runtime adoption” returned no directly applicable MAF decision; the cited spike files were inspected manually outside that retrieval selection.
