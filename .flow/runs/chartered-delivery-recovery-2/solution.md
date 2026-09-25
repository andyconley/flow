# Solution: Chartered v8 Delivery Recovery, chunk 2

Status: **Option A chosen by the engineer on 2026-09-24.**

## Problem

Under C1 (Flow-owned evidence only; checkpoints non-authorizing), the only v8 uncertain row that can be resolved safely is a producer or verifier action left `started` or `unknown` that has a stored `response_observations` row. That row exists after a crash, or a failed `complete()`, between `observe_response` and `complete` (`research/solution-verify.md`). Every other uncertain row cannot be resolved, and the operator must be told so plainly:

- any unresolved manager call, because Flow observes and completes a manager call in one transaction;
- an action with no stored response.

## Applicable rules

- **ADR 0012 (Flow-owned MAF recovery), lines 11 and 15.** Operator resolution is append-only. Completion needs a Flow-owned durable observation, and a lost response may stay blocked. This is the basis of C1 and of Option A's explicit resolution.
- **ADR 0016 (chartered v8 recovery).** Eligibility is decided read-only and refuses on uncertain rows. The lock order is `recovery_lock`, then `run_lock`, then `send_lock`, then SQLite. Option A leaves both unchanged.
- **`standards/architecture.md` "Domain and integration boundaries".** The resolve route stays at the gateway boundary, and the ledger stays the single writer of resolution state.
- **`standards/orchestration.md`.** The fenced, authority-guarded route and the validation-before-mutation pattern.
- **`standards/security.md`.** Trust stops at the local uid. The worktree guard closes the path by which a worker could write evidence.

## Options

### Option A: operator-confirmed reconcile through a v8 `resolve-execution` route (chosen)

- **Shape:** v8 `resolve-execution`:
  1. takes the non-blocking `recovery_lock` (refusing with `attempt_running` or `recovery_in_progress`), then `run_lock` through the delivery authority guard;
  2. compares a caller-supplied expected owner generation;
  3. resolves one `started` or `unknown` producer or verifier action to `resolved_completed` using only its stored `response_observations` row, which it re-validates against the envelope and action in the same transaction;
  4. appends a `recovery_resolutions` row at the **current** owner generation, without bumping it.

  The current generation is already in the recovery chain (the envelope's lead-claim generation or the latest recovery generation), so there is no spurious interruption and the chain stays continuous (Q4). The operator then runs `recover-delivery-lead`. A resolved verifier is evaluated with no resend through the existing boundary (f) path (`delivery_gateway.py:1054-1066`).
- **Pros:**
  - No ADR 0012 change.
  - It delivers approved requirement 1.
  - It keeps chunk 1's eligibility and claim unchanged.
  - Completion stays an explicit, audited act.
  - The receipt rule (f) already counts `operator_resolved_*`.
- **Cons:** an operator step that adds no information, and a new CLI route to secure.
- **Reversibility:** high. It is additive.

### Option B: automatic reconcile during recovery

- **Shape:** eligibility treats an uncertain action with an observation as reconcilable. The chunk 1 claim completes it at the new generation, writing a Flow-authored resolution.
- **Pros:** a single operator command, and no new route.
- **Cons:**
  - It needs an ADR 0016 amendment.
  - It makes the 1a claim transaction more complex.
  - It needs a new resolution kind in the receipt rule (f) and in inspection.
  - Recovery would complete work without an explicit operator act.
- **Reversibility:** medium.
- **Not chosen.** A reasonable later refinement once A has run in practice.

### Option C: A plus trace-backed resolution for Claude producers (rejected)

- It needs a new trace binding (an action-bound file name and a digest recorded at send) for a narrow crash window, and it helps Claude producers only.
- Deferred as a separate follow-up if that window is ever hit.

## Decision

- **Option A** (engineer, 2026-09-24).
- **Amendments to the approved definition** (they follow from Option A and the verification):
  - **Drop requirement 3** (manager-call resolution) and its manager extensions to requirements 7 and 9. Manager blockers are "abandon only". Q5 is moot.
  - **Drop requirement 2's trace route**, and merge requirements 2 and 6 into one reconcile requirement.
  - **Add a worktree guard:** `execute_chartered_delivery` (and prepare) refuses a worktree that contains the project's `.flow/` directory, which closes the A4 gap.
  - **The ACs follow:**
    - AC1 (a) becomes an "abandon only" test;
    - AC4 (manager atomicity) is removed;
    - AC5 merges into AC1 (c)/(e);
    - AC8 is narrowed to action resolutions;
    - a worktree-guard AC is added.

## Session model advice

- **Coordinator recommendation:** the `judgment` profile, `claude-opus-4-8` at high effort. A consequential recovery design under ADR constraints; resolved from the configured profiles.
- **Active parent:** declared by the session environment as Opus 5.5 (`claude-opus-5-5[1m]`), not observed by Flow.
- **Effective delegated assignments:** `solution-verify` → solution-architect (opus, medium). Definition reviews: product-manager and business-analyst (sonnet, medium), solution-architect and security-reviewer (opus, medium).
- **Switch performed:** no.

## Proposed chunks

One PR (C3 keeps the hardening in chunk 2), with two commit groups, each leaving the suite green:

1. **Guards and hardening:**
   - the worktree guard;
   - the v8 refusal in `regrant_not_dispatched` (C2);
   - `send_lock` opened with `O_NOFOLLOW`;
   - the MAF-gated tests reading `FLOW_MAF_PYTHON`;
   - a test showing an `unknown` manager call alone blocks a lead change.
2. **Reconcile:**
   - the v8 `resolve-execution` route (fence, expected-generation check, observation-only resolution at the current generation);
   - the resolution-binding check at continuation (kind, id, attempt, chain generation);
   - `recovery.resolutions` in the receipt;
   - inspection guidance for each blocker: "resolve-execution (stored response)" or "unresolvable; abandon only";
   - a refusal that points to inspection;
   - lead changes after resolution;
   - boundaries (c) and (e), with and without a stored response;
   - boundary (a) as abandon-only;
   - an ADR 0016 amendment for the v8 route;
   - the AC12 mutation checks.

## Risks (owned)

- **R1. A resolution recorded at the current generation could be read as outside the chain by the receipt validator.**
  - Owner: lead-developer.
  - Mitigation: an AC3 test runs resolve, then recover, then seal, and validates the receipt. A mutation that records at a bumped generation must fail it.
- **R2. The operator passes the main checkout as the worktree for an attempt prepared before the guard.**
  - Owner: engineer.
  - Mitigation: the guard runs in prepare and in the resolve route. Existing attempts are refused on resolution if their envelope's worktree contains `.flow/`.
- **R3. An orphaned provider child keeps editing after `resolved_completed` (security S3).**
  - Owner: lead-developer.
  - Mitigation: the resolve route's `attempt_running` refusal covers the live run. Recovery's existing worktree drift check (AC7) refuses if the diff moved. The plan confirms that the drift check runs after resolution.
- **R4. Manager-call and unobserved-action blockers leave some attempts permanently blocked.**
  - Owner: engineer. Accepted under ADR 0012.
  - Mitigation: inspection says "abandon only", and abandonment stays open.
- **R5. `resolve_unknown` accepts only `unknown`/`allowed`, not `started`.**
  - Owner: lead-developer.
  - Mitigation: the v8 route accepts `started` only under the fence (the approved requirement 1 invariant). v5–v7 keep today's check.

## Suggested design artifacts

- An ADR 0016 amendment: the v8 `resolve-execution` route, resolution at the current generation, observation-only evidence, and manager calls abandon-only.
- No spike is needed; the verification note covers the unknowns.

## Next lane

- **`flow-plan`.** The approach is chosen and the open forks are closed:
  - Q3: operator-confirmed;
  - Q4: current generation, no bump;
  - Q5: moot.

  The remaining work is shaping commits and tests.
