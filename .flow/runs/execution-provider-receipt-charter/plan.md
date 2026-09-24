# Plan: Minimal Codex SDK and MAF capability spike

- Work item: `execution-provider-receipt-charter`
- Plan scope: first chunk of the approved [solution](solution.md), as narrowed by Andy on 2026-09-19
- Status: Approved scope; implementation pending

## Problem and outcome

Flow's maintainer needs enough observed evidence to choose the least-effort next execution approach without building a worker runner prematurely. Inspect the Codex Python SDK capability surface and run a tiny Microsoft Agent Framework (MAF) stub workflow. Produce a reproducible comparison and a recommendation for the next live proof. This spike cannot decide that subscription-backed worker execution or receipts already work.

## Scope

1. Create a disposable Python environment outside Flow's runtime/install. Record Python, `openai-codex`, and MAF package versions and the exact commands used. A missing package or blocked install is an observed preflight outcome, not evidence an API lacks a capability.
2. Inspect the Codex SDK's public import/API surface without creating a worker turn, prompt, or model call. Check exposed interfaces for work directory, sandbox, approval mode, thread/session IDs, events/results, interruption, and resume. Classify each as observed, documented only, absent in inspected version, or unverified. Read a non-secret local auth-status signal only if available without launching a worker; never collect credentials.
3. Run one deterministic MAF workflow with a stub executor. Exercise start-to-terminal, one pending approval/request and bounded response, and one checkpoint/resume path. Simulate a Flow-side delegated-authority denial outside the charter envelope; MAF carries the request/response but never decides authority. Use public APIs and no Codex agent or model.
4. Compare a minimal Flow-only path with the MAF stub using concrete integration steps, dependencies, state stores, reconciliation paths, and code that would still have to be owned by Flow. Choose by least implementation effort that preserves Flow's authority and receipt boundary, without a numeric score.
5. Write one run-local spike report with commands, versions, bounded output references, findings, decision, uncertainty, and the smallest required live follow-up. Do not promote the recommendation into an accepted ADR until a live worker proof supports it.

## Outside this spike

- No real Codex worker, model request, prompt, subscription exercise, worktree, Git mutation, production provider, or receipt.
- No production Flow schema, CLI lifecycle, gate, authority, storage, router, or runtime dependency change.
- No real Shaper approval. The charter policy denial is a deterministic simulation only.
- No claim that effective sandbox grants, Codex session events, interruption, MAF/Codex interoperability, or receipt capture are proven.

This narrows the [solution](solution.md)'s proposed live reuse spike at Andy's direction. Its live worker and receipt exit criteria are **deferred**, not satisfied by this plan.

## States and contracts

- Preflight: `available`, `missing`, or `blocked` per dependency, with exact version/error and a stop decision.
- SDK capability: `observed`, `documented_only`, `absent_in_version`, or `unverified` per interface. Do not infer effective runtime behavior from an import or signature.
- MAF stub: `started`, `pending_request`, `checkpointed`, `resumed`, and `terminal`, or a bounded failure with error evidence. A separate Flow-side simulated policy result is `allowed` or `denied`; only a denial case is required here.
- Decision: `keep_flow`, `adapt_maf_for_live_probe`, or `defer_maf`, with evidence and explicit remaining uncertainty. The decision concerns the **next test**, not production engine selection.
- Report format: `research/reuse-spike.md` under this run; prototype source and sanitized command output can live under `research/spike/` and be linked from the report. No credentials, raw environment dumps, or unbounded transcripts.

## Validation and stop rule

- Another engineer can run the documented commands in a fresh disposable environment and get the same capability inventory and MAF stub state transitions, or a clear dependency-blocked result.
- Verify no Codex worker/model turn, repository worktree, or Flow lifecycle mutation occurs. Inspect the final Git delta and package environment location.
- Demonstrate the MAF stub's pending-request/resume and the Flow-side out-of-envelope denial. If a public MAF API cannot do that in the inspected version, record the exact limitation and stop rather than expanding the spike.
- Review the report's claims against captured evidence. List subscription use, effective permissions, real-worker interruption, and actual receipt trust as unverified follow-up tests.
- Stop after one deterministic MAF path and the capability inventory. Do not add retries, multiple agents, routing, or broader frameworks.

## Ownership and next lane

- Implementation: lead developer, using a disposable environment and run-local report.
- Validation: test engineer reviews reproduction and state/claim distinctions; architect reviews the effort recommendation and Flow boundary.
- Next lane: `flow-implement` for this bounded spike because it includes a runnable stub, dependency inspection, durable evidence, and a decision handoff across files. No production runner is authorized by this plan.

## Session model advice

- Coordinator recommendation: working (`gpt-5.6-terra`, medium effort), provisional mapping; bounded planning with clear proof. Availability unverified.
- Active parent: unknown; no verified same-session identity supplied by `flow model context`.
- Effective delegated assignments: business-analyst and product-manager (`gpt-5.6-terra`, medium), architect (`gpt-5.6-sol`, medium), separate from coordinator advice.
- Switch performed: no.
