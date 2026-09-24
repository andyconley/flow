# Definition: First execution contract and Shaper charter

- Work item: `execution-provider-receipt-charter`
- Definition lead: Codex coordinator
- Opening role: solution-architect
- Status: Approved by Andy Conley on 2026-09-19 (`approve-definition`)
- Approver: Andy Conley

## Problem or opportunity

- What: Flow can validate declared assignments and handback artifact presence, but has no contract that binds an actual worker attempt and resulting repository state to those declarations.
- Who: The engineer/operator dispatching a Codex worker, the later Delivery Lead, and the reviewer deciding whether to accept, rework, or escalate.
- Why now: A single-worker execution path is the next proposed slice. Its authority and evidence boundaries need agreement before runner design.

## Desired outcome

One authorized Codex assignment can produce a reviewable attempt receipt for one isolated worktree. The operator can identify the authorized work, the actual attempt, its resulting commit or explicit no-commit outcome, validation results, remaining uncertainty, and the next decision from the charter, receipt, and referenced artifacts alone.

## Evidence

- Research needed: yes, focused on the current dispatch/handback boundary.
- Research notes: `research/full-session-review.md`, `research/current-boundary.md`, and `research/microsoft-routing.md`.
- Archive retrieval: `no_matches`, selection `8bd330694ec9fd17626fbf927e365d3350e4a8e891d2b9a6ab29cb1bf53978e0`; repository evidence was manually inspected outside that selection.

## Requirements

### Success criteria

- A single-worker handback is independently reviewable without using unstructured worker chat as the authoritative record. Execution ownership remains open pending a reuse spike.
- Missing or contradictory execution evidence produces a blocked or unsuccessful disposition, never an accepted success claim.
- The new contract extends Flow's existing orchestration and lifecycle semantics without adding a second lifecycle owner.

### Provider execution contract

- Correlate dispatch with stable work ID, assignment ID, provider identity, unique attempt ID, and the approved manifest/brief/input revision or digest.
- Declare required capabilities with confirmed/missing/unknown status before launch; missing or unknown required capability prevents dispatch.
- Bind the worker to one isolated worktree, baseline commit, allowed read/write scopes, expected output, validation plan, and bounded execution/resource policy. Record the actual runtime/session identity and attempt start/end or interruption.
- Provider-specific launch details may vary, but the logical outcome and evidence fields must remain usable by another provider later.
- Keep the agent harness/execution provider (initially Codex), inference runtime/provider (such as a direct paid model or later Ollama/LM Studio), routing policy/deployment, requested model/profile, and observed underlying model as separate identities. A routed attempt records the actual model when the provider reports it; otherwise it records `unknown` rather than treating the router name as the model. This is compatibility for later routing, not a requirement to build a router in this slice.
- An unattended worker that needs permissions outside its grant stops with a blocked outcome and an escalation request; it cannot obtain interactive approval or expand its own scope.

### Execution receipt contract

- Each attempt emits an immutable, uniquely identified receipt with correlation to the dispatch and a controlled terminal outcome: completed, partial, failed, cancelled, or interrupted. Exact representation and vocabulary are solution decisions, provided these distinctions survive. A coordinator/provider-side observer, outside the worker's write scope, records the authoritative attempt facts; worker-authored statements remain claims.
- Record the observed worktree/repository identity, baseline commit, resulting commit for a successful changed-work handback, or explicit no-commit reason. Record process/session reference and exit/termination result when the provider exposes them.
- Record declared outputs, independently observed changed paths, validation command or check identifiers and observed results, evidence/log references, unexpected changes, unresolved work, and safe next action. Missing or skipped validation carries a reason. The observed baseline-to-result delta includes committed, uncommitted, and untracked changes; symlinks and path escapes cannot hide changes outside authorized scopes.
- Link each required validation result to the charter acceptance criterion or gate it addresses. Specific CRAP, mutation, or coverage thresholds are project policy decisions, not defaults imposed by this contract.
- A successful handback requires a verifiable resulting commit, output/evidence references that resolve, and complete observed scope/delta disposition. Unknown or out-of-scope changes block success pending an authorized disposition. An unsuccessful attempt may retain a no-commit receipt for diagnosis but cannot satisfy the success handback gate. A solely worker-authored or tampered receipt cannot satisfy success.
- Separate attempt outcome from claims about correctness. Use Flow's observed/inferred/recommended/unverified claim provenance and reconciliation; artifact presence or worker prose alone never proves semantic truth or runtime permission compliance.

### Shaper charter contract

- Capture the proposed or agreed outcome, audience, in/out scope, constraints and non-goals, success and acceptance criteria, required evidence, confidence target, accepted risks, hard delivery budgets (delegations, concurrency, retries, resource use), stop condition, delegated decisions, prohibited decisions/actions, escalation triggers, and accountable decision owner. Record whether it is still shaping or aligned, the authorizing decision/event, and the approved revision when aligned.
- Reference approved run artifacts and their revision rather than restating them as a competing source of truth. Changes to outcome, acceptance criteria, scopes, gates, or limits require the authority named by the applicable Flow lifecycle and charter rules. Andy approved this definition; future routine Shaper approvals within an approved delegation envelope remain an intended capability to define separately.
- The charter must be usable without an automated Shaper agent. A replacement coordinator can tell which decisions are delegated and which require Andy.

### Non-goals

- Delivery Lead or Shaper runtime automation; autonomous approval of Flow lifecycle gates.
- Multiple workers/providers, local-model routing, parallel teams, automatic retry/recovery, MCP or remote notifications.
- Implementing a dynamic model router, including Microsoft Foundry Model Router, in the first worker path. Evaluating Microsoft Agent Framework as an execution orchestrator is part of the pre-design reuse spike, not a commitment to its routing features.
- Semantic verification of worker claims or proof of hidden runtime permissions by the existing structural validator.
- Implementing the user-controlled, Git-capable, off-machine-backup-ready artifact store in this contract slice. The store is a user-stated architectural requirement; `.flow/runs/<work-id>/` is only a proposed temporary first-slice location and must not be adopted as the final topology by default.

### Constraints

- Preserve ADR 0001: `run.json` remains a small lifecycle projection; detailed execution data belongs in a linked, versioned contract/artifact.
- Reuse stable assignment/provider identities, scope rules, claim provenance, reconciliation, and dispatch/handback gates in the current orchestration contract.
- Fail closed on ambiguous correlation, missing required evidence, unconfirmed capability, or unauthorized scope change. Do not allow a worker to change its own charter or judging criteria.
- Exclude credentials and sensitive values from durable receipts and referenced evidence by default, including command arguments, environment, paths, logs, validation output, commit metadata, and failure diagnostics. Use bounded, access-controlled references and sanitized summaries; do not make raw worker transcript the receipt.

### Assumptions

- One isolated worktree and commit-bound successful handback are required for the first execution slice, as proposed in the supplied conversation. Engineer approval of this draft will confirm them.
- A failed or interrupted attempt needs a durable diagnostic receipt even when it does not reach a successful handback gate.
- Run-local artifact storage may serve a temporary first proof only if it has a defined migration path to the user-owned durable store. Keep durable artifacts separate from runtime checkpoints, cache, and credentials.

### Open questions

- Solution lane: exact serialization/linkage of the receipt and charter; choose an approach that honors ADR 0001 and the logical fields above.
- Later routing lane: compare Microsoft Foundry's model selection and other routers with Flow's local/paid routing goals, including model eligibility, portability of session history, availability, privacy, cost, and observed-model reporting. Keep this distinct from the MAF orchestration spike.
- Solution lane: precise detection and disposition of out-of-scope changes, dirty worktrees, missing commits, and provider interruption.
- Engineer: specify which routine stage approvals may be delegated to a future Shaper and which are human-only. Current Flow gate requirements remain in force for this definition.
- Engineer: decide whether the first Codex worker must use a local model, or whether direct Codex execution can prove the worker/receipt path before local inference is added.
- Engineer: decide whether a temporary run-local first proof is acceptable, or whether the user-owned artifact store must precede execution. The eventual separate, backup-ready store is already user requested.
- Solution lane: run a bounded MAF reuse spike against one worker and the known over-delegation failure before selecting a Flow-owned runner. Compare subscription-backed Codex/Claude, local model path, checkpoint ownership, Flow policy gates, and receipt capture with current official documentation and a live minimal test.

## Research implications

- Existing manifest identities and scope declarations -> correlate receipts rather than duplicate authority.
- Structural validator limits -> explicitly separate observed attempt facts from accepted correctness claims.
- ADR 0001 -> keep execution detail outside `run.json`.
- No demonstrated worker launcher -> define one provider path before routing or teams.
- Router research -> preserve distinct provider, router, and underlying-model identities now; evaluate model-routing mechanisms after the single-worker receipt is trustworthy. MAF's orchestration fit is evaluated before choosing the execution engine.
- Full shared-chat review -> distinguish harness from model runtime, preserve delegated routine approval, encode hard delegation budgets and stop conditions, record Shaper alignment provenance, and keep validation traceable to acceptance without importing a fixed quality-tool policy. The MAF reuse proposal requires a spike before custom runner design.

## Adversarial review

- Product: Worth defining now as a narrow learning slice; prevent receipt fields from implying semantic proof. Scope limited to one Codex worker.
- Requirements: Require distinct terminal outcomes, attempt identity, failure/no-commit evidence, and reviewable references. A file existing is not a successful handback.
- Architecture/capability: Preserve ADR 0001 and provider-neutral logical fields. Treat serialization, launch mechanism, and long-term artifact topology as later solution decisions.
- Security: Require an observer outside the worker's write scope for authoritative attempt facts; compare the complete observed delta with authorized scopes; keep secrets out of receipts and referenced evidence. Reassess external access and credential handling in solution.

## Next lane

- A bounded MAF-vs-Flow reuse spike, then `flow-solution`, because execution ownership, storage order, serialization, provider launch, worktree enforcement, and artifact linkage have multiple viable approaches. The open questions above remain solution decisions.
