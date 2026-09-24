# Research note: smallest worthwhile increment of chartered delivery recovery

## Outcome and value

Today only protocol v5 can resume or recover an interrupted attempt; v8, the current chartered path, cannot, and a crash or `unknown` verifier outcome strands the attempt in `started`/`unknown` requiring manual operator reconciliation (`maf-adoption-design.md` residual risk; `structured-verifier-contract/archive.md` follow-up). This blocks unattended delivery and is a hard prerequisite for adoption step 5 (delegated Shaper expansion approval): any mid-run pause for approval must be resumable without breaking the authority chain (ADR 0014 fencing) or the pause itself becomes an unrecoverable stall. Shaper approval cannot be trusted to gate execution until the gated attempt is guaranteed to resume correctly on either side of the gate. **Implication:** requirements must state resume/recovery as an explicit precondition for step 5, not a parallel or optional track.

## Recommended slice boundary

**In scope:** v8-only resume and recovery, operator-invoked, extending `resume_delivery`/`recover_delivery` to accept v8 attempts. Cover the recovery matrix cell that is the top named follow-up: a crash between verifier-call completion and evaluation, reusing recorded verifier input/output/test evidence rather than resending or re-running the test (whose output includes timing and therefore changes digest — `archive.md:43`, `structured-verifier-contract/archive.md:35`). Chartered v8 attempts must be correctly marked `interrupted` (currently excluded from that path — brief line 15).

**Explicitly deferred:**
- v6 and v7 resume. Design doc states v6 records are historical/inspectable-only and v8 is "the current chartered path" (line 19); v7 is superseded. Resuming frozen protocols risks changing their historical meaning, which the brief forbids. **Implication:** requirements should scope resume to v8 attempts only; v6/v7 stay inspectable-only, non-goal for this increment.
- Automatic resume. ADR 0014: "Resume or supersede must be explicit; elapsed time never transfers ownership." **Implication:** requirements must specify operator-invoked resume via CLI, matching the existing v5 pattern, not a background auto-resume trigger.
- Lost-response `unknown` handling (send-side ambiguity, not completion-to-evaluation ambiguity). Two predecessor archives flag this as unresolved and evidence-gated: "Flow cannot establish provider-side exactly-once execution" (`maf-restart-reconciliation/archive.md`, `maf-post-resolution-continuation/archive.md`). This is a different, harder problem than reconciling a completed-but-unevaluated verifier call. **Implication:** requirements must name this a non-goal here to avoid scope creep into an unresolved exactly-once question; only the "completed, not yet evaluated" recovery path is in scope.
- Cancellation and operator diagnostics — explicitly deferred to adoption step 5 and by the engineer's framing decision.
- A live proof run — explicitly deferred by the engineer's framing decision and separable from contract correctness (see below).

## Success criteria (capability level)

- `resume_delivery` and `recover_delivery` accept v8 attempts and correctly reject/no-op on v6/v7 without altering their stored meaning (regression-tested, matching the AC8 regression precedent in `structured-verifier-contract/archive.md`).
- A v8 attempt killed after verifier-call completion but before evaluation reconciles on restart using only recorded evidence: zero new provider sends, deterministic re-evaluation, correct terminal state.
- A defined set of process-kill boundaries (queued, started, completed-unevaluated, `unknown`) each reconcile to the correct state on restart with zero extra provider calls, mirroring the boundary matrix already proven for v5 (`maf-restart-reconciliation`).
- Full repository suite plus new focused recovery tests pass; v5/v6/v7 behavior unchanged.

## Honest non-goals

Automatic/unattended resume; v6/v7 live resume; lost-response exactly-once resolution; cancellation; operator diagnostics; enforced token/dollar caps; MCP ingress; delegated Shaper approval itself.

## Does a controlled live run belong in this increment's acceptance?

No. The recovery contract's correctness (idempotent replay, evidence reuse, correct terminal states) is provable with recorded/stubbed evidence, as prior recovery slices (`maf-restart-reconciliation`, `maf-post-resolution-continuation`) already demonstrated without a live Ollama call. A live run tests a separate, orthogonal risk — real verifier output against the strict v8 contract, which the predecessor archive flags as unproven and possibly high-`unusable`-rate. Conflating the two would make this increment's acceptance depend on an unrelated and already-flagged-risky variable. **Implication:** keep the live run as its own later slice per the design doc's "not yet built" list.

## Reasons to defer or reject

Implementation must wait for the v8 branch (`codex/structured-verifier-contract`) to merge to `main` — the engineer decision explicitly scopes this run to definition only, ahead of that merge. Defining now is still worthwhile because the recovery matrix design doesn't depend on the merge, but no code should land until it does. **Implication:** requirements/plan should mark implementation-start as gated on the merge event, not on this run's acceptance.
