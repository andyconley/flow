# Solution: First execution contract and Shaper charter

- Work item: `execution-provider-receipt-charter`
- Status: Recommended approach accepted by Andy Conley on 2026-09-19; implementation and spike evidence pending
- Definition: [requirements.md](requirements.md), [acceptance-criteria.md](acceptance-criteria.md)
- Archive selection: `0ecc8cc8c8dcab5c32050b80e081aaf3e86e0240a68239f1390b487cdbf123f2` (one current hit on session-model advice; no execution precedent returned)

## Confirmed problem and decisions

Flow needs a verifiable handback from one subscription-backed Codex worker without surrendering its lifecycle, scope, evidence, or approval authority. The first proof may use run-local files, provided receipt identity and links can migrate to the later user-owned, Git-capable artifact store. The solution must include delegated Shaper approvals, bounded by an approved charter. Andy confirmed these three decisions and accepted the recommended Flow-owned approach, subject to a bounded Microsoft Agent Framework (MAF) reuse spike.

The approved definition listed autonomous lifecycle-gate approval as a non-goal and future routine Shaper approval as an intended capability. The later explicit solution-scope clarification means this solution **designs and proves bounded delegated approval**; it does not authorize a generic runtime, worker, or agent to bypass existing gates. A charter revision and authority matrix must state which exact transition/decision is delegated, to whom, for how long, under which budget and risk limits, and what remains human-only. Until that policy is implemented and separately verified, existing CLI gates and engineer approval requirements remain in force. This clarification needs a traceable acceptance case in the implementation plan.

## Applicable rules and precedent

- `scaffolds/default/standards/architecture.md` — **Layering**, **Domain and integration boundaries**, and **ADR convention**: keep charter policy and receipt validation deterministic; translate Codex or MAF data at adapters; record the execution-ownership and storage decisions in an ADR.
- `scaffolds/default/standards/orchestration.md` — **Required artifact**, **Agent briefs and assignments**, **Claim provenance and reconciliation**, and **Lifecycle enforcement**: use the existing manifest IDs, scopes, capability confirmation, dispatch/handback gates, and provenance; structural checks do not prove semantic truth or hidden runtime grants.
- `docs/architecture.md` — **Project Overlay** and **Source-of-Truth Rule**: `run.json` stays a small lifecycle projection; detailed execution and authorization evidence are linked artifacts. This also honors ADR 0001.
- `scaffolds/default/standards/solutioning-decisions.md` — **Decision criteria**: compare architectural fit, operational cost, reversibility, testability, and scope before selecting execution ownership.
- Archive hit `session-model-recommendation` — current advice is advisory and does not change parent models or add gates. It applies to this consultation, not to execution ownership. Manually inspected repository standards and ADR 0001 are outside that archive selection.

## Options

| Option | Shape | Benefits | Costs and risks | Reversibility |
| --- | --- | --- | --- | --- |
| A. Flow coordinator + Codex Python SDK | Flow validates charter/manifest, creates worktree and attempt ID, invokes Codex in that workspace, observes Git and validation independently, and seals a run-local receipt outside worker write scope. | Direct fit with the existing Python CLI and lifecycle gates; one authoritative policy/evidence state; subscription-backed Codex is the first provider. | Flow owns attempt supervision, interruption handling, and the eventual recovery path. SDK authentication, sandbox, event, and approval behavior require a live probe. | High if provider and storage adapters remain behind stable contracts. |
| B. MAF workflow + Codex executor | Flow owns policy and durable receipt; MAF owns workflow execution, checkpointing, and pending requests; a Codex adapter executes the worker. | MAF has documented workflow checkpoints and human-input primitives that may help later multi-worker delivery. | A second execution state must be reconciled; native Codex harness integration is unverified; Flow still owns authority and independent evidence. More dependency surface for one worker. | Medium; checkpoint formats and orchestration semantics can spread. |
| C. Direct Codex CLI subprocess | Flow launches the CLI and parses a bounded result into the same receipt contract. | Few dependencies and a useful fallback. | Process/output handling and session events may need custom code; evaluate only if SDK probe fails. | High. |

## Recommendation and boundaries

Choose **A** for the first proof, conditional on a bounded MAF comparison and a Codex SDK capability probe. MAF may replace future execution mechanics if the spike shows a material reduction in Flow-owned code without weakening its policy, evidence, or subscription requirements. Neither MAF nor Codex owns Flow lifecycle transitions or Shaper authority.

```text
Shaper charter + approved Flow manifest
                 |
       Flow policy/gate evaluator
                 |
       attempt + workspace adapter
                 |
        Codex Python SDK worker
                 |
 independent Git/validation observer
                 |
  immutable receipt -> Flow handback gate
```

**Domain and interfaces:** Define provider request/outcome, attempt receipt, and delegated decision records in Flow-owned schemas. Use an SDK adapter for runtime-specific session, sandbox, and event details. Provider launch, model choice, and router identity remain separate.

**State and persistence:** Keep `run.json` as lifecycle projection and `orchestration.json` as assignment authority. Place first receipts under the run through a storage locator and stable IDs/digests; keep them outside worker write scope. Distinguish durable artifacts from resumable runtime checkpoints, cache, and credentials. A migration proof must move a receipt to a user-owned store and still resolve its references.

**Approval:** The Flow evaluator checks charter revision, approver identity, permitted action/transition, scope, risk, budgets, expiry/revocation, and accepted-risk/stop conditions before recording a delegated decision. Deny ambiguous or enlarged authority and escalate to Andy. MAF human-input events, if used later, carry requests and responses but are not the authority source. Existing gate semantics change only through an explicit, reviewed implementation.

**Operational shape:** One worker, one isolated worktree, one commit-bound successful handback. Missing/unknown capability or evidence blocks dispatch or success. A failed/interrupted attempt retains a diagnostic receipt. No multi-worker scheduler or model router is introduced in this slice.

## Bounded reuse spike and exit criteria

Before runner planning, compare a minimal Codex SDK attempt with a minimal MAF workflow wrapping Codex. Use a disposable repository and the existing subscription sign-in. Verify actual auth mode without exposing credentials, working directory/worktree, sandbox and approval behavior, session/attempt identifiers, terminal events, interruption, checkpoint/resume, and whether an independent Flow observer can produce the approved receipt. Inspect the installed MAF package/API for a native Codex harness integration rather than assuming it exists or does not. Exercise one delegation-limit denial and one pending approval. Record code size, dependencies, state reconciliation, and operational burden. The spike must recommend KEEP Flow, ADAPT with MAF, or DEFER MAF against these observations; documentation alone is insufficient.

Official documentation currently supports a stable Codex Python SDK driving local app-server and Codex's ChatGPT subscription sign-in. MAF documents checkpoints and external request/response handling. None of that proves this installed environment's subscription-backed SDK or MAF adapter behavior; the spike closes that gap.

Sources: [Codex SDK](https://developers.openai.com/es-419/docs/codex-sdk), [Codex authentication](https://developers.openai.com/es-419/docs/auth), [MAF workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/workflows), [MAF human input](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop), [MAF checkpoints](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints).

## Proposed chunks for planning

1. **Reuse and capability spike:** produce the observed comparison above and an ADR recommendation. No production runtime adoption yet.
2. **Flow contract and delegated-policy slice:** versioned provider/receipt/charter schemas, authority matrix, decision record, fail-closed checks, and acceptance tests for allowed, expired, prohibited, and budget-exceeded decisions. Existing gates continue to apply until this slice is accepted.
3. **Single Codex worker slice:** worktree preparation, SDK adapter, independent observer, sealed receipt, scope/validation checks, and handback gate integration. Include success, blocked permission, failure/no-commit, tamper, and unauthorized-delta cases.
4. **Storage migration proof:** locator and stable references, migrate a run-local receipt to the user-owned store prototype, then verify identity and evidence resolution. Full store productization is separate.

These are proposed planning slices, not authorization to dispatch a worker or implement them now. The spike may revise the execution adapter choice without changing the approved logical contracts.

## Owned risks

| Risk | Owner | Mitigation |
| --- | --- | --- |
| SDK auth or sandbox differs from docs/current desktop setup | Lead developer | Run a disposable live capability probe before adapter design; record auth mode and effective grants without secrets. |
| Worker changes receipt, scope, or judging criteria | Security reviewer | Keep observer/receipt outside worker scope; compare full committed, uncommitted, untracked, and symlink-resolved delta; test tampering. |
| Delegated approval exceeds Andy's charter | Solution architect | Define an explicit deny-by-default authority matrix, revision binding, budget/expiry checks, revocation, and audit evidence; retain human-only actions. |
| MAF checkpoint state conflicts with Flow history | Architect | Spike interruption and resume; require Flow to remain decision authority and document reconciliation before adoption. |
| Run-local evidence becomes stranded during store migration | Data engineer | Use stable IDs/digests and a locator; exercise migration and readback before full store design. |

## Design artifacts and next lane

- Spike report using `scaffolds/default/templates/spike-template.md`.
- ADR for execution ownership and storage boundary after the spike.
- Versioned provider, receipt, charter, and delegated-decision contracts plus an authority matrix.
- Sequence diagram for dispatch, worker handback, approval, and blocked escalation.
- Next lane: `flow-plan` for the bounded spike first; subsequent slices depend on its result.

## Session model advice

- Coordinator recommendation: judgment (`gpt-5.6-sol`, high effort), provisional mapping; architecture and authority consequences justify stronger judgment. Availability is unverified.
- Active parent: unknown; `flow model context` supplied no verified same-session identity.
- Effective delegated assignment: solution-architect (`gpt-5.6-sol`, medium effort) for option review, separate from coordinator advice.
- Switch performed: no.
