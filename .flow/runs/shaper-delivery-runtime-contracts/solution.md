# Solution: Runtime-neutral Shaper and Delivery Lead contracts

- Work item: `shaper-delivery-runtime-contracts`
- Status: Approved 2026-09-22 by Andy Conley
- Decision: Flow-owned canonical contracts with projection into the existing supervised Magentic gateway
- Decision date: 2026-09-22

## Problem

Flow needs a runtime-neutral boundary between shaping and delivery. The Shaper owns definition and optional solutioning. At an explicit transition, Flow seals the approved intent into a Delivery Charter and grants one Delivery Lead authority to plan, implement, review, and archive within that charter. ChatGPT Work, Claude Code, and Codex operate from the same Flow state. MAF/Magentic coordinates only Flow-authorized specialists, and Codex, Claude, and Ollama remain bounded providers.

## Applicable rules

- `scaffolds/default/standards/architecture.md` — **Layering**: keep contract and policy logic testable without MAF or provider dependencies.
- `scaffolds/default/standards/architecture.md` — **Domain and integration boundaries**: translate runtime, provider, checkpoint, and legacy formats at adapters.
- `scaffolds/default/standards/architecture.md` — **ADR convention**: ownership, compatibility, versioning, and integration boundaries require a durable ADR.
- `scaffolds/default/standards/orchestration.md` — **Required artifact** and **Lifecycle enforcement**: Flow's manifest and lifecycle gates remain authoritative.
- `scaffolds/default/standards/orchestration.md` — **Claim provenance and reconciliation**: runtime/session observations cannot become authority without qualified evidence.
- `docs/adr/0011-supervise-maf-behind-flow-gateway.md`: retain one Flow-owned gateway and a separately supervised MAF runtime.
- `docs/adr/0012-flow-owned-maf-recovery.md`: reconcile Flow state before restore and use generation fencing for uncertain execution.

## Options considered

### Option A: Canonical Flow contracts with execution projection — selected

**Shape:** Add canonical `ShaperContract`, immutable `DeliveryCharter`, ownership-handoff, and Delivery Lead claim records. At `start-plan`, project the sealed charter into a new execution-envelope version for the existing gateway, ledger, MAF supervisor, adapters, and receipts.

**Pros:** Clear domain boundary; runtime-neutral; reuses current control plane; keeps MAF replaceable; makes cross-runtime continuation artifact-based; supports inspect-only legacy records cleanly.

**Cons:** Adds new schemas, a projection layer, and distinct current/legacy readers.

**Reversibility:** Medium-high. The contracts and projection are Flow-owned, while the execution runtime remains replaceable.

### Option B: Extend v6 into the Delivery Charter — rejected

**Shape:** Add Shaper, ownership, amendment, and continuation fields directly to the existing v6 execution envelope.

**Pros:** Smaller initial code change.

**Cons:** V6 already couples provider choices, Python test command shape, allowed/write paths, roster size, and narrow job semantics. It would make an execution transport the domain model and complicate inspect-only compatibility.

**Reversibility:** Low-medium.

### Option C: New event-sourced orchestration aggregate — rejected

**Shape:** Derive charter, ownership, amendments, and evidence from a new event store.

**Pros:** Strong audit model.

**Cons:** Duplicates C-Lite lifecycle and execution-ledger responsibilities, creates a second kernel, increases migration/operational cost, and delays usable functionality.

**Reversibility:** Low.

## Recommended architecture

### Domain boundaries

Flow owns these canonical domain records:

- `ShaperContract`: versioned definition/solution intent, evidence, authority, constraints, and approval lineage.
- `DeliveryCharter`: immutable delivery authority derived from the latest approved Shaper-owned artifacts.
- `OwnershipHandoff`: append-only Definition-to-Delivery event binding exact source digests.
- `DeliveryLeadClaim`: one active, generation-fenced owner for a delivery attempt.
- `CharterAmendment`: approved new charter version plus linked delivery epoch; prior versions and attempts remain immutable.

Execution envelopes, MAF checkpoints, provider payloads, runtime sessions, local paths, and credentials are projections or observations. They are not domain authority.

### Transition and ownership

1. `approve-definition` and optional `approve-solution` preserve their approved artifacts.
2. `start-plan` becomes the atomic Shaper-to-Delivery boundary:
   - verify approved inputs and expected run revision;
   - canonicalize and seal the Delivery Charter;
   - append one ownership-handoff event;
   - create the delivery attempt and generation-fenced Delivery Lead claim;
   - transition the lifecycle to planning.
3. Identical replay returns the existing charter/handoff/claim. Changed source bytes or stale revision fail without another transition.
4. One Delivery Lead generation may mutate or dispatch for an attempt. Resume or supersede is explicit and increments the generation.
5. A timeout or stale heartbeat may set `attention_required`; elapsed time alone never grants takeover or permits a send.
6. Unknown actions must be reconciled before a successor generation can dispatch related work.

### Identity and continuation

Keep these identities separate:

- logical operator/principal;
- Flow run, Shaper Contract, Delivery Charter, attempt, and owner generation;
- runtime instance/session;
- host, project, source revision, and worktree binding;
- provider credential/session.

Authority binds only to Flow IDs, artifacts, approvals, and current generation. Before mutation, every runtime validates run revision, charter digest/version, phase, attempt, owner generation, pending approvals/unknowns, source identity, and project/worktree binding. Chat transcripts and provider sessions remain advisory observations.

### Execution projection

A versioned adapter converts the Delivery Charter into a new execution envelope consumed by the existing Flow gateway and supervised Magentic runner. Unsupported charter features fail before attempt creation. Every Magentic manager or specialist proposal returns through Flow for a one-use grant. Provider results are normalized and sealed into receipts linked to the charter, handoff, owner generation, worktree evidence, diff, tests, and independent verifier.

### V6 compatibility

- Preserve historical v6 bytes.
- Add a tolerant read-only inspector that returns normalized known fields, diagnostics, and capability flags such as `readable`, `executable`, and `resumable`.
- Valid v6 records are inspectable with `executable: false` and `resumable: false` through the new path.
- Malformed or digest-mismatched records remain visible with diagnostics but never become dispatch-eligible.
- Do not rewrite v6 records into the new schema or pass them through the new dispatch validator.

### Runtime surfaces

ChatGPT Work, Claude Code, and Codex call the same Flow application service and use the same run/charter state. ChatGPT Work local access is treated as established. Runtime binding is still validated before mutation. Ordinary Chat MCP ingress and secure tunneling remain deferred.

## Reconciled requirement clarifications

- The approved feasibility-probe criterion is superseded by Andy Conley's explicit solution-engagement decision: ChatGPT Work local access is established and no feasibility probe is required. This solution records the supersession without rewriting the approved definition history.
- V6 records must remain readable and inspectable. They do not need execution or resume support under the new contract.
- A material amendment creates both a new immutable charter version and a linked delivery epoch.
- One active Delivery Lead per attempt is enforced through durable generation fencing and explicit resume/supersede events.

## Proposed chunks

### Chunk 1: End-to-end contract and execution proof

1. Add canonical schemas and stable digests for Shaper Contract, Delivery Charter, ownership handoff, and Delivery Lead claim.
2. Make `start-plan` atomically seal the charter, append the handoff, and claim one fenced Delivery Lead generation.
3. Add a new execution projection into the existing gateway, ledger, supervised Magentic runner, adapters, and receipts.
4. Add v6 inspection with explicit execute/resume refusal.
5. Prove one small real Flow repository change: Magentic selects an approved Claude or Codex producer; Flow observes the bounded diff and test; a distinct Ollama verifier checks it; Flow seals a receipt tied to charter, handoff, generation, and evidence.

This is the first independently mergeable slice. It proves useful functionality rather than adding another contract-only rung.

### Chunk 2: Cross-runtime continuation

Add shared inspect/resume commands and adapters for ChatGPT Work, Claude Code, and Codex using expected run revision, charter digest, owner generation, and verified project/worktree binding. Add stale-state and competing-runtime conflict handling.

### Chunk 3: Amendments and delivery epochs

Route material change requests back to Shaper authority. Approval creates charter version N+1 and delivery epoch N+1, halts affected older work, and preserves lineage.

### Chunk 4: Delegated expansion and nested providers

Add scoped Shaper expansion decisions, provider substitution, and nested Claude/Codex subagent controls. Every nested call receives its own Flow grant and receipt. Ollama retains no spend/token caps while remaining subject to scope, concurrency, and safe-stop policy.

### Chunk 5: Operational hardening and Work integration

Add cancellation, trace correlation, operator diagnostics, recovery matrix coverage, and Work-facing ingress over the same application service. Ordinary Chat MCP remains a separate future definition.

## Cost posture

The first slice uses deterministic tests for normal validation and one bounded live acceptance job. It needs one paid producer path selected from Claude or Codex and one local Ollama verifier, with no extra feasibility smoke or repeated provider proof. Flow records observed usage and retains existing time, scope, concurrency, and no-automatic-retry controls.

## Risks and owners

- **Contract bloat** — Owner: Flow contract owner. Mitigation: keep canonical records separate from execution projections and cap fields/artifacts.
- **Split-brain Delivery Leads** — Owner: Flow state owner. Mitigation: transactional expected revision, owner generation fencing, and explicit supersession.
- **Unknown call repeated after takeover** — Owner: recovery owner. Mitigation: reconciliation gate before successor dispatch.
- **V6 accidentally reactivated** — Owner: compatibility owner. Mitigation: dedicated inspection parser and negative execute/resume tests.
- **MAF or provider details leak into domain schemas** — Owner: runtime owner. Mitigation: adapter-only projection and conformance tests.
- **Cross-runtime project/path drift** — Owner: adapter owner. Mitigation: validate source identity and local binding before mutation.
- **Producer/verifier identity collapse** — Owner: evidence owner. Mitigation: stable definition digests, distinct assignments, and receipt validation.
- **First slice becomes too broad** — Owner: plan lead. Mitigation: constrain the live proof to one small Flow change and defer general continuation, amendments, nested providers, and operational hardening.

## Required design artifacts

- ADR: Shaper-to-Delivery ownership, canonical contract boundary, generation fencing, amendment epochs, and v6 inspection-only policy; reference ADR 0011 and ADR 0012.
- Versioned JSON schemas/contracts for Shaper Contract, Delivery Charter, handoff, lead claim/resume/supersede, and execution projection.
- Main-path and crash/supersession sequence diagrams.
- Charter-version, delivery-epoch, and owner-generation state diagram.
- Compatibility matrix for inspect, execute, resume, and amend behavior by version.

## Session model advice

- Coordinator recommendation: judgment profile, provisionally `gpt-5.6-sol` at high effort; selected because mistakes would reshape durable contracts and boundaries. Availability remains unverified.
- Active parent: unknown; no verified same-session identity was supplied.
- Effective delegated assignments: solution-architect -> `gpt-5.6-sol` medium; architect -> `gpt-5.6-sol` medium; test-engineer -> `gpt-5.6-terra` medium.
- Switch performed: no.

## Evidence posture

The solution-lane archive search was unavailable because the isolated worktree lacks `.flow/identity.json`. Selection ID: `501cb460009fad788b24907928f7763278186434f5db141dbf9eca7c4bf02141`. Repository contracts, tests, standards, and ADRs were inspected manually outside that retrieval selection.

Architect and test-engineer advisory expertise queries returned `no_match`; no advisory entries were injected and no disposition was required.

## Next lane

After explicit solution approval, use `flow-plan` to shape Chunk 1. Do not plan later chunks until the end-to-end proof has passed its acceptance gate.

## Approval record

- Decision: Approved
- Approver: Andy Conley
- Date: 2026-09-22
- Risk disposition: Owned through the named owners and mitigations in this solution.
