# Plan: Chunk 1 Shaper-to-Delivery execution proof

- Work item: `shaper-delivery-runtime-contracts`
- Status: Shaped plan accepted by engineer; lifecycle approval pending
- Work type: high-risk, multi-module runtime contract change
- Target lane: `flow-implement`

## Problem statement

- **What:** Flow lacks a canonical, runtime-neutral contract that atomically transfers approved Shaper intent to one fenced Delivery Lead and drives the existing Magentic runtime.
- **Who:** Flow maintainers and operators using ChatGPT Work, Claude Code, or Codex.
- **Why now:** The architecture is approved, and the next slice must prove useful delivery rather than add another isolated contract layer.

## Desired outcome

Flow takes approved Shaper intent, seals a Delivery Charter at `start-plan`, grants one generation-fenced Delivery Lead, lets Magentic explainably choose an approved Claude or Codex producer, verifies a bounded real Flow change with Ollama, and seals a complete charter-linked receipt.

## Scope

### In scope

- Canonical Shaper Contract, Delivery Charter, ownership handoff, and Delivery Lead claim schemas and digests.
- Atomic and idempotent `start-plan` ownership transition under a per-run lock.
- One active owner generation with explicit resume/supersede and unknown-call reconciliation rules.
- Protocol-v7 projection into the existing gateway, ledger, supervised Magentic runner, adapters, checkpoints, and receipts.
- Structured, bounded Magentic rationale for choosing Claude or Codex from the approved producer roster.
- Read-only v6 inspection with explicit execute/resume refusal.
- `flow run inspect-delivery WORK_ID [--attempt-id ID] [--json]`.
- ADR 0014, CLI/help documentation, deterministic tests, and one live producer-plus-Ollama handback job.

### Out of scope

- Broad cross-runtime continuation adapters.
- Charter amendments and linked delivery epochs beyond reserving identifiers/lineage fields.
- Nested Claude/Codex subagents and delegated Shaper expansion.
- New scheduler, DAG engine, execution ledger, or broad provider abstraction.
- Ordinary Chat MCP, tunneling, or Work-local-access feasibility testing.
- V6 migration, execution, or resume.
- Broad cancellation and operational recovery redesign.

## Required states and invariants

### Lifecycle and ownership

- `definition_approved` or `solution_approved` -> atomic `start-plan` -> `planning`.
- Delivery Lead claim status: `active`, `attention_required`, `released`, or `superseded`.
- Exactly one active owner generation per logical delivery attempt.
- Stale generation cannot mutate lifecycle, grant, dispatch, resume, or seal a receipt.
- Elapsed time can mark `attention_required`; it cannot transfer ownership.
- Resume/supersede is explicit, increments generation, and respects unresolved/unknown actions.

### Transition commit point

- Hold a per-run `fcntl` lock.
- Read and hash the approved requirements, acceptance criteria, optional solution, and orchestration manifest.
- Build and validate canonical artifacts in memory.
- Stage immutable artifact files under the run.
- Atomically replace `run.json` once with planning state and bindings to the charter, handoff, logical delivery attempt, and lead claim.
- Treat this `run.json` replacement as the authority commit point.
- Append/reconcile `events.jsonl` idempotently after the commit; unreferenced staged files before the commit are inert.
- Do not promise cross-file or filesystem-plus-SQLite ACID. The execution-ledger attempt is created later immediately before dispatch and must match the run bindings.

## Contract expectations

### Shaper Contract

Canonical Flow-owned artifact derived from the approved definition and optional solution. It carries stable ID/version/digest, approved source references/digests, outcome, scope, exclusions, constraints, acceptance, evidence, authority, risk, and approval lineage. Runtime sessions and provider credentials are observations, not authority.

### Delivery Charter

Immutable artifact derived from the Shaper Contract. It carries stable ID/version/digest, delivery outcome, source/worktree policy, read/write scopes, tools, eligible specialists, provider capabilities, limits, approval matrix, producer/verifier rules, validation, recovery/retry, handback, and compatibility version.

### Ownership handoff and lead claim

The handoff binds exact source digests and the lifecycle transition. The claim carries logical delivery attempt ID, owner actor/runtime identity, generation, status, acquisition/supersession lineage, and charter digest. Local paths and sessions do not authorize ownership.

### Magentic selection rationale

The accepted producer action records:

- eligible producer assignments considered;
- selected assignment, provider, model, role, and specialist-definition digest;
- bounded reason codes based on charter-visible facts, such as capability fit, allowed tools/scope, provider availability, and producer/verifier separation;
- bounded reasons for non-selected candidates.

Flow validates that the selected producer is eligible and that referenced facts exist. The rationale explains the choice but cannot grant or expand authority. After one producer result is accepted, a second producer action is denied.

### V6 inspection

Preserve raw historical bytes. A dedicated tolerant reader returns normalized known fields, integrity diagnostics, and capability flags. Valid v6 records report `readable: true`, `executable: false`, `resumable: false`. Malformed or digest-mismatched records remain inspectable to the extent possible but are never dispatch-eligible.

### CLI inspection

`inspect-delivery` shows current contract/charter version and digest, source digests, lifecycle phase, logical and execution attempt, active owner generation/status, pending unknowns/approvals, selection rationale, and compatibility diagnostics. It performs no mutation or dispatch.

## Implementation sequence and ownership

### A. Domain contracts and ADR

- New: `cli/delivery_contracts.py`
- New: `tests/test_shaper_delivery_contracts.py`
- New: `docs/adr/0014-shaper-delivery-ownership.md`
- Define canonical builders, strict validators, IDs, digests, schema tables, and compatibility capabilities.

### B. Atomic lifecycle handoff

- New: `cli/delivery_control.py`
- Modify: `cli/runstate.py`, focused lifecycle tests in `tests/test_flow.py` or new `tests/test_delivery_control.py`.
- Add per-run locking, staging, commit-point behavior, idempotent replay, stale-input refusal, lead status, resume, and supersede rules.

### C. V6 inspection compatibility

- New: `cli/legacy_delivery.py`
- New: `tests/test_legacy_delivery.py` and tracked fixtures under `tests/fixtures/`.
- Implement tolerant inspection and hard refusal for new execute/resume paths.
- May proceed alongside B after A stabilizes the normalized inspection shape.

### D. Protocol-v7 projection and ledger links

- New: `cli/delivery_projection.py`
- Modify: `cli/execution_contracts.py`, `cli/execution_ledger.py`.
- New: `tests/test_delivery_projection.py`, `tests/test_delivery_lead_claims.py`, and crash-boundary coverage.
- Link execution attempts to logical delivery attempt, charter digest, and owner generation. Require current generation on every mutation. Add ledger fields additively.

### E. Gateway and Magentic integration

- Modify: `cli/delivery_gateway.py`, `runtime/maf_runner/delivery_lead.py`.
- Modify chartered/Magentic/recovery tests.
- Load sealed charter/claim through `delivery_control`, project only after all validation, retain existing `_execute_prepared_delivery`, allow both approved Claude/Codex producers, validate/seal comparative rationale, accept only one producer, then require a distinct read-only Ollama verifier.

### F. CLI, documentation, and inspection

- Modify: `cli/flow.py`, `README.md`, `docs/cli-reference.md`, `docs/maf-adoption-design.md`, generated help surfaces as required by repository checks.
- Add `inspect-delivery` and actionable v6 refusal messages.
- Add CLI and documentation-contract tests.

### G. Acceptance job

- After deterministic gates pass, select the smallest suitable real Flow change available at implementation time.
- Selection criteria: low risk, isolated paths, clear observable behavior, targeted test, clean isolated worktree, and independent reviewability.
- Charter both Claude and Codex producers. Magentic chooses one and records why. Flow observes the diff and targeted test. Ollama independently verifies. Seal the receipt and run the full suite.

## Acceptance boundary

Chunk 1 is complete only when this chain is evidenced:

`approved Shaper intent -> sealed Delivery Charter and one lead claim -> explainable Magentic producer choice -> Flow-granted producer action -> Flow-observed diff/test -> distinct Ollama verification -> charter-linked sealed receipt`

The prior ChatGPT Work feasibility-probe criterion is superseded by the engineer's later decision that Work local access is established. It is not a Chunk 1 gate.

## Session model advice

- Coordinator recommendation: judgment profile, provisionally `gpt-5.6-sol` at high effort, because the plan spans durable lifecycle, schema, recovery, and provider boundaries.
- Active parent: unknown; no verified same-session identity was supplied.
- Effective delegated assignments: business-analyst -> `gpt-5.6-terra` medium; product-manager -> `gpt-5.6-terra` medium; architect -> `gpt-5.6-sol` medium; test-engineer -> `gpt-5.6-terra` medium.
- Switch performed: no.

## Recommended lane

`flow-implement`. The work spans multiple modules, sessions, persistence and concurrency boundaries, CLI/documentation surfaces, deterministic validation, and a live acceptance job.
