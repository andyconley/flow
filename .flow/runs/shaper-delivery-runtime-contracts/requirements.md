# Proposed requirements: Shaper and Delivery Lead runtime contracts

Status: **Approved 2026-09-22 by Andy Conley**

## Ownership model

1. The **Shaper** owns Definition: problem framing, outcomes, scope, exclusions, constraints, acceptance criteria, evidence, risks, specialist eligibility, delegation authority, open decisions, and required approvals. It operates through `flow-define` and may use `flow-solution` before approval or amendment.
2. The **Delivery Lead** owns Delivery after an explicit transition: `flow-plan`, `flow-implement`, `flow-review`, and `flow-archive`. It may plan, sequence, delegate, checkpoint, recover, and replan only inside the sealed charter.
3. **Flow** owns lifecycle state, schemas, immutable artifacts and digests, gates, approvals, policy, dispatch grants, receipts, recovery, evidence, and acceptance eligibility.
4. **MAF/Magentic** coordinates the Flow-authorized roster. It cannot grant provider access, change the charter, accept work, or make Flow state authoritative inside MAF.
5. **Codex, Claude, and Ollama** remain bounded provider adapters. Every consequential call enters through a Flow grant and produces normalized evidence.

## Runtime-neutral Shaper contract

The Shaper artifact MUST carry:

- `schema_version`, `shaper_contract_id`, `run_id`, `version`, `status`, and canonical digest;
- problem, intended users, outcomes, scope, exclusions, constraints, assumptions, and acceptance criteria;
- source evidence with provenance and claim status;
- risks, open decisions, and decision owners;
- allowed specialist roles/capabilities and prohibited capabilities;
- delegation and approval matrix, including delegated expansion limits;
- budget/safety envelope using only enforceable controls and explicitly identified observations;
- artifact and worktree boundaries;
- amendment lineage and approval history;
- next-lane eligibility.

Shaper research MAY use guarded Magentic coordination before approval only when Flow grants each research specialist call, records its evidence, and prevents research output from becoming approval or delivery authority.
Research outputs MUST be tagged advisory or proposed, MUST use recorded read/write scopes, and MUST NOT mutate a candidate charter except through an explicit Shaper edit recorded by Flow.

## Delivery Charter

Approval MUST produce an immutable, canonical Delivery Charter snapshot containing:

- `schema_version`, `charter_id`, `charter_version`, `run_id`, `delivery_attempt_policy`, and charter digest;
- source Shaper contract ID/version/digest and approved requirements/acceptance/solution artifact references and digests;
- approved outcomes, scope, exclusions, constraints, acceptance criteria, and unresolved risks accepted for delivery;
- eligible specialist definitions by stable role/definition digest and maximum instances;
- allowed provider capabilities and bindings without making a provider mandatory unless approved;
- delegation, concurrency, replan, runtime, tool, path, output, and retry limits;
- producer/verifier separation and validation obligations;
- escalation, stop, cancellation, unknown-call reconciliation, and recovery rules;
- approved artifact/worktree boundaries and required handback/receipt content;
- approver identity, approval event, amendment lineage, and compatibility version.

## Definition-to-Delivery transition

1. Transition requires explicit approval of the proposed requirements and acceptance criteria and successful Flow lifecycle gates.
2. Flow emits one durable transition event that binds the approved source artifacts to the Delivery Charter digest.
3. Approval and transition are idempotent: replay returns the existing sealed charter or fails without creating a second active delivery.
4. A draft may be explicitly withdrawn, superseded, or abandoned before dispatch. Cancellation before first dispatch produces no provider send and no executable delivery attempt.
5. Definition remains authoritative for meaning; Delivery becomes authoritative for execution within that meaning.
6. Only one Delivery Lead may hold the durable ownership lease for a delivery attempt. Flow defines lease identity, expiry/termination, and the evidence required to resume or supersede after a crash.
7. The Delivery Lead MUST NOT silently change outcomes, scope, exclusions, permissions, acceptance criteria, evidence obligations, risk posture, provider eligibility, or budget/safety boundaries.
8. A material change halts affected delivery work and creates a versioned amendment for Shaper/engineer approval. The old charter and evidence remain immutable and linked.

## Cross-runtime continuation

1. ChatGPT Work, Claude Code, and Codex MUST resolve the same run and charter through stable Flow identifiers and canonical artifacts.
2. Runtime chat/session history is advisory context, never authoritative state.
3. Each runtime appends qualified evidence and receipts to the same Flow run. It may not clone or fork a run silently.
4. A continuation MUST display or validate run ID, charter digest/version, current phase, active attempt, pending approvals, and unresolved/unknown calls before mutation.
5. Flow serializes competing lifecycle mutations from different runtimes and returns a conflict or stale-state diagnostic without duplicating work.
6. The active runtime MUST prove a compatible local project/worktree binding. Machine-local paths are observations, not portable authority; an unavailable binding stops with an actionable diagnostic.
7. Authentication and local filesystem access remain runtime adapter concerns; they MUST NOT create a separate policy path.

## Provider substitution

1. A provider-specific charter requirement remains pinned until an approved amendment changes it.
2. A capability-based charter MAY allow a compatible provider replacement, but Flow must re-evaluate eligibility and issue a new grant before dispatch.
3. An unapproved or ungranted replacement is an out-of-charter substitution and produces zero provider sends.

## Compatibility and reuse

1. Reuse the current ledger, orchestration manifest, dispatch gateway, chartered launcher, receipts, checkpoints, and recovery controls.
2. Existing accepted chartered jobs remain readable. Migration is additive and versioned; unsupported records fail with an actionable compatibility diagnostic.
3. MAF state remains linked execution state. Flow records remain authoritative and must be sufficient to inspect eligibility, decisions, provenance, and recovery posture without trusting an active MAF process.
4. Malformed, partially migrated, or digest-mismatched legacy records MUST remain ineligible for dispatch.

## Explicitly unresolved requirements

- **ChatGPT Work adapter and locality:** The target remains a run shaped in ChatGPT Work, refinable in Claude Code, and deliverable in Codex from the same Flow state. Before its implementation acceptance is fixed, a bounded feasibility probe must establish which Work surface can read/write canonical local Flow artifacts, how it binds the same project/operator, and what cross-machine behavior is supported. Owner: solution/implementation lane.
- **Delivery Lead lease mechanics:** Identity, duration, heartbeat/expiry, and supersession representation require solution design against existing Flow recovery state. Owner: solution architect.
- **Amendment epoch model:** Decide whether an approved amendment creates a charter version, linked delivery epoch, or both. Owner: solution architect with engineer approval.
