# Research: first runnable MAF adoption slice

- Owner role: business-analyst
- Date: 2026-09-19
- Confidence: High for scope and Flow ownership; Medium for the local-worker launch details pending the implementation plan.

## Question

What must the first implementation slice deliver after the approved decision to
adopt MAF behind a supervised Flow gateway, when its first runnable milestone
is one guarded local worker launched through the Flow CLI?

## Method and sources

- User planning decisions recorded in this session: first foundation/contract
  slice; one local guarded worker through Flow CLI; Codex, Claude, and MCP in
  later slices.
- [MAF adoption design](../../../../docs/maf-adoption-design.md), especially
  the target boundary, integration contract, and first two adoption slices.
- [ADR 0011](../../../../docs/adr/0011-supervise-maf-behind-flow-gateway.md).
- [Flow run lifecycle](../../../../cli/runstate.py) and
  [architecture documentation](../../../../docs/architecture.md), which
  establish the project overlay as canonical and `flow run transition` as the
  lifecycle writer.
- The MAF spike handbacks, particularly
  [multi-turn policy gate](../../maf-multiturn-policy-gate/HANDOFF.md) and
  [Magentic interruption](../../maf-magentic-interruption/HANDOFF.md).

## Problem statement

- **Observed request:** Start Flow's MAF adoption with a foundation/contract
  slice whose first runnable result is one local guarded worker started from
  the Flow CLI.
- **Underlying job:** Let an operator run a bounded unit of specialist work
  while Flow remains the authoritative record of authorization, lifecycle,
  evidence, and recovery state. MAF may coordinate the call, but must not gain
  an independent way to dispatch it.
- **Why now:** The architecture direction and supervised-runner boundary are
  approved. The existing spikes proved individual controls in run-local
  prototypes but left no production contract or CLI path.

## Scope

### In scope

1. Project-owned, versioned domain records for a charter/envelope snapshot,
   execution attempt, action intent, Flow decision and one-use dispatch grant,
   checkpoint reference, normalized result, and sealed execution receipt.
   Records persist under the existing project run artifacts and have a clear
   storage boundary so a later database migration does not change their public
   meaning.
2. A Flow CLI execution entry point that attaches an attempt to an **existing**
   Flow run. It validates required input identity and invokes an optional,
   separately supervised local MAF runner through a versioned local protocol.
3. A sole Flow gateway/factory for the slice's MAF participants. It accepts a
   Flow specialist specification, constructs the guarded participant, and
   rejects direct raw MAF Agent/Executor injection on the Flow launch path.
4. One allowed local specialist instance. Before any worker invocation, the
   gateway persists the action intent and policy decision, issues a scoped
   one-use grant, then invokes the local adapter. The worker's normalized
   result returns through the gateway.
5. The initial deterministic policy envelope: local provider allowlist, one
   specialist role, and Flow-owned delegation/concurrency/replan limits. This
   slice need only exercise one delegation; its records must retain the limits
   needed by later multi-worker work.
6. A receipt that distinguishes proposed, authorized, dispatched, observed,
   failed, and `unknown` work, and links the charter/envelope, specialist
   definition and instance, policy decision, runner/checkpoint reference,
   normalized result, and artifact hashes.
7. Clear local failure behavior: unavailable optional runtime, malformed or
   incompatible runner protocol, denied action, worker failure, and runner
   exit all leave a Flow-visible attempt/result state without advancing C-Lite
   lifecycle state outside `flow run transition`.

### Out of scope

- Codex, Claude, paid-model accounting, or mixed-provider execution.
- MCP ingress, ChatGPT/Claude transport surfaces, and any second policy path.
- Multiple workers, parallelism, producer/verifier handoffs, Shaper expansion
  approvals, or a full 13-specialist compatibility proof.
- Multi-turn restart/replay completion beyond recording the stable identifiers
  and checkpoint reference that the next recovery slice needs.
- A Flow-native DAG engine, scheduler, or checkpoint system.
- Changing the project run lifecycle schema or treating MAF checkpoints as
  Flow's source of truth.

## Requirements and acceptance criteria

| ID | Requirement | Testable acceptance evidence |
| --- | --- | --- |
| R1 | Flow owns the execution-domain records and their stable IDs. MAF payloads remain adapter data. | Unit schema round trips cover valid and invalid records without MAF installed. A persisted attempt includes `run_id`, attempt ID, charter/envelope and manifest identity, and format versions. |
| R2 | The CLI only starts an attempt against a valid existing Flow run and retains C-Lite as lifecycle authority. | CLI integration tests reject absent/invalid runs and do not create dispatch state. A successful launch adds execution artifacts but lifecycle writes still occur only through `flow run transition`. |
| R3 | The supervised runner has one versioned local start/event/result protocol and cannot self-grant dispatch. | Contract tests reject an unknown protocol version and a runner action without a Flow grant. A runner process receives only the immutable envelope and grant data needed for its call. |
| R4 | Every worker request crosses the Flow gateway before the adapter is called. | An allowed local request produces, in order, action intent, policy decision, grant, dispatch observation, normalized result, and receipt. A denied request yields zero adapter calls. |
| R5 | Flow's application launch path cannot accept a raw MAF participant. | A direct MAF Agent/Executor supplied to the Flow gateway/factory is rejected; the one allowed specialist is constructed from a Flow definition and unique instance identity. |
| R6 | One local guarded worker can complete from the Flow CLI. | An isolated project-overlay integration test launches the runner, invokes one configured local worker, records its observed provider identity and output/artifact hash, then emits a verifiable receipt. Test doubles are labeled `local-stub`; they cannot satisfy the observed-local-worker criterion. |
| R7 | The first receipt is independently interpretable. | Receipt validation proves links to the exact charter/envelope, definition digest, action/decision/grant IDs, checkpoint reference or explicit absence, result status, and artifact hashes. It rejects a claimed provider call with no dispatch observation. |
| R8 | Failures remain recoverable and honest. | Tests cover runner launch failure, worker failure, and termination after grant. Each produces an explicit Flow attempt/result state; post-dispatch uncertainty is `unknown`, with no automatic retry or untracked continuation. |
| R9 | The slice can be used without adding MAF as a mandatory Flow dependency. | Core CLI and schema/policy tests pass with MAF unavailable; the CLI reports a specific remediation when the optional runner/runtime is absent. |

## Assumptions and remaining ambiguities

| Status | Item | Evidence needed to resolve it |
| --- | --- | --- |
| Decided | The first provider class is local and paid adapters are disabled. | User planning choice and ADR 0011. |
| Assumed | The first local worker uses an existing Flow specialist definition, likely a bounded implementation or test role. | Planner should identify the smallest compatible definition and its artifact contract. |
| Not yet defined | The exact CLI spelling, runner executable/package boundary, and local transport endpoint. | Lead developer should propose names consistent with `cli/flow.py`; architect should select the smallest versioned protocol. |
| Not yet defined | Whether the observed local backend is Ollama or another configured local inference service, and how availability is discovered. | Implementation plan must name the supported backend and an offline test double. |
| Not yet defined | Where sealed receipt storage and artifact observation live relative to the worker's writable workspace. | Architecture plan must define permissions and an independent observer boundary. |
| Deferred | Durable replan IDs and restart-safe replay beyond `unknown` reconciliation. | The recovery slice must prove separate-process replay before enabling multi-turn work. |

## Handoff evidence

- The approved boundary and record fields come from
  [docs/maf-adoption-design.md](../../../../docs/maf-adoption-design.md) and
  [ADR 0011](../../../../docs/adr/0011-supervise-maf-behind-flow-gateway.md).
- Existing lifecycle ownership is directly observed in
  [cli/runstate.py](../../../../cli/runstate.py) and
  [docs/architecture.md](../../../../docs/architecture.md).
- The raw-participant, replay, and replan risks are observed in the cited
  [multi-turn handback](../../maf-multiturn-policy-gate/HANDOFF.md) and
  [interruption handback](../../maf-magentic-interruption/HANDOFF.md).
- The implementation plan should use this file as the acceptance baseline;
  it should not claim provider, restart, or receipt behavior already exists
  in production.
