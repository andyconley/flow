# Solution options: chartered delivery recovery

- Role: solution-architect. Date: 2026-09-23. Code: v8 worktree `verifier-contract`. G = `cli/delivery_gateway.py`, L = `cli/execution_ledger.py`, C = `cli/delivery_control.py`, X = `cli/execution_contracts.py`. **O** = observed, **I** = inferred.
- Binding inputs: engagement answers 1 to 5 and decisions D1 to D4. I **confirm answer 3 with one refinement**: the successor gets a durable, digest-bound link to its fenced predecessors. It reuses none of their evidence, and it counts their paid and verifier sends against the same limits (R4).

## Code facts that shape the options

- An attempt stays `started` until `finish_attempt`, and `decide` accepts only `started` for v8 (L:319, L:1242) (O). A same-attempt resume therefore needs no status widening.
- v5 "interrupted" means the ledger still says `started` plus an `interruption.json` file. Chartered attempts are excluded (G:986-992) (O).
- `_claim_recovery_locked` already covers v8: it bumps the generation and turns `started` into `unknown` (L:250-276) (O). But two racing claims both succeed, so it does not yet fail closed (I).
- `resolve_unknown` resolves **actions only**. `recovery_resolutions.action_id` references `actions` with foreign keys on (L:100, L:191, L:899-901) (O). An unknown **manager call** therefore cannot be resolved today. A manager response is observed and completed in one step (L:595), so an unknown manager call never has an observation (O).
- Chartered limits are counted from rows per attempt (L:364-418) (O). A regranted row counts once. A successor attempt starts at zero (I).
- `prepare_chartered_delivery` already mints a fresh attempt from the charter baseline, using the current lead generation (G:344-414) (O).

## Option A (recommended): resume the same attempt, with an interruption state

- **Shape.** A v8 attempt that loses transport, or ends with uncertain sends, stays `started`. It gets an append-only **ledger** interruption record and no receipt. `resume-delivery-lead` claims a new fence, reconciles the ledger, rebuilds evidence from durable records, restores the latest bound MAF checkpoint, and continues in place. One `receipt.json` is sealed, with a `recovery` block.
- **Keeping one receipt.** `finish_attempt` stays the only seal commit point. A receipt file the ledger has not committed is a draft: recovery replaces it and records the draft's digest. The ledger stores the sealed receipt's SHA-256.
- **Successor links.** The v8 envelope gains an optional `predecessors` list at creation: `[{attempt_id, terminal_status, receipt_sha256, lead_generation}]`. `create_attempt` verifies each predecessor is terminal and its digest matches. Because the receipt binds `envelope_digest`, the link is tamper-evident. The task facts (G:761) list the predecessors' outcomes.
- **Pros:**
  - Mirrors the v5 same-attempt path.
  - Makes no change to the v5 epoch or ADR 0013 semantics.
  - Keeps limits on action rows.
  - Keeps one seal point.
- **Cons:**
  - Adds a new non-terminal state for inspection to explain.
  - Adds a manager-call resolution table in chunk 2.
- **Reversibility:** high. The tables and receipt fields are additive and v8-only.

## Option B: widen the v5 continuation epochs to v8, with one receipt

- **Shape.** Each recovery is a `continuation_epochs` row with its own fence (`claim_continuation`, L:1393) and its own grants (`continuation_grants`). The epoch attaches to a non-terminal attempt, so `receipt_sha256` must become nullable (L:125). The final `receipt.json` lists the epochs. There is no `continuation-*.receipt.json`.
- **Keeping one receipt.** The G:1049-1056 linked-path branch is suppressed for v8.
- **Successor links.** Same as Option A.
- **Pros:**
  - Reuses the per-epoch fencing and the lineage policy counting (L:1286-1296).
- **Cons:**
  - Epochs assume a terminal original receipt (L:1330-1344; ADR 0013).
  - One epoch per action (`UNIQUE(attempt_id,action_id)`) conflicts with multi-boundary recovery.
  - `continuation_grants` sit outside the rows that v8 `decide` and verifier allowance count (L:386-396). Limits would have two sources.
  - Needs `decide` widened at L:319 and the v2 lookup at L:1329 avoided.
- **Reversibility:** low to medium. It overloads shared v5 schema and semantics.

**Option C, mirroring v5 exactly** (same-attempt resume, plus an epoch with a linked receipt after `unknown`): rejected. It violates engagement answers 1 and 2.

## Boundary handling in Option A

| Boundary | Handling |
|---|---|
| (b) unconsumed grant | An `allowed` grant with no dispatch events (L:936 check) becomes `not_dispatched`, reason `recovery_unconsumed_grant`. It is regranted under chartered `decide` limits: the same row, counted once. |
| (d) producer done, no verifier input | Re-verify the edit (deterministic, G:543-545). Run the test **once** (G:778-782 today). |
| (f) verifier done, not evaluated | The replay path evaluates from the binding (G:866-879) (O). |
| (g) retry-eligible evaluation | Test evidence comes from the final binding's `test_digest`. The retry is gated at L:405-410 (O). |
| (h) terminal evaluation | Evidence is reused. The MAF restore replays; the manager tail is granted normally. |
| (i) sealing | A new ledger event `runtime_outcome_recorded` is written before the receipt is built. If present, recovery skips MAF and seals. |
| Clean transport loss | An interruption record with `cause=transport`. Resumes like (b) to (h). |
| (a) manager unknown (chunk 2) | Blocked until a new `resolve_unknown_manager_call` exists, bound to the call, attempt, and generation. `completed` replays via G:803-806, `not_dispatched` regrants. |
| (c) producer unknown (chunk 2) | Existing `resolve_unknown`. Operator-supplied evidence is validated, then observed (the v5 G:716 precedent). Fresh test. |
| (e) verifier unknown (chunk 2) | Consumes allowance (L:814). `completed` evaluates the recorded response. The `test_digest` is reused. |

**Evidence reuse rule** (replaces G:778-782 for v8):
- If a verifier input exists, the test evidence is `{command: job.test.argv, status: passed, output_sha256: the final binding's test_digest}`. `prepare_verifier_send` runs only after a passing test (G:562) (O).
- If the re-verified diff differs from the binding's `diff_digest`, recovery fails closed with `worktree_drift` (AC7).

## Five dimensions for Option A

These dimensions come from this role. `architecture.md` has no section named for them, so each is cited by the closest section.

1. **Domain boundaries** ("Domain and integration boundaries", "Domain rules"):
   - The ledger owns attempt state and resolutions. `run.json` owns lead authority. The gateway orchestrates.
   - Build the receipt in a pure `delivery_receipts.py` shared by the gateway and the supersede path. Recovery eligibility becomes a pure function over a snapshot.
   - This avoids a C to G import cycle; G already imports C (I).
2. **Interfaces and data flow** ("Layering"):
   - The CLI routes v8 in `resume_delivery` and `recover_delivery` to `_resume_chartered`, which never calls v5 fixtures.
   - `inspect-delivery` projects eligibility, blockers, and the evidence each blocker needs.
   - Operator evidence is normalized at the boundary, not passed through raw.
3. **State and persistence** ("Core principles: prefer reversible decisions"):
   - New append-only tables: `attempt_interruptions`, `attempt_recoveries`, and `manager_call_resolutions`.
   - New events: `runtime_outcome_recorded`, `recovery_unconsumed_grant`.
   - `finish_attempt` gains `superseded` and a `sealed_receipt_sha256` column. v8 refuses `unknown`.
   - The envelope gets an optional `predecessors` field. v5 to v7 are untouched.
4. **Operational shape** ("Domain rules": deterministic and testable):
   - A non-blocking per-attempt recovery `flock`, plus an `expected_generation` compare-and-swap on the claim. The second caller gets `recovery_in_progress`.
   - Lock order is `run_lock` then `send_lock`, matching G:811.
   - The lead-change guard reads ledger `started` and `unknown` rows, replacing the inert C:239.
   - Supersede order: ledger `superseded` seal first, then the `run.json` claim bump.
   - `prepare_chartered_delivery` refuses to start while any sibling attempt is non-terminal.
5. **Decision durability** ("ADR convention": data ownership, domain boundaries): this is durable, so it needs ADR 0016.

## Recommendation

**Option A.** It wins on:
- reversibility (additive, v8-only);
- blast radius (the v5 epochs and ADR 0013 are untouched);
- a single source for limits (action rows);
- time to deliver (reuses L:250 fencing and the G:859-887 replay).

Option B's only advantage is lineage counting. Option A covers that for successors through `predecessors`.

## Proposed chunks

**Chunk 1: evidence-free boundaries.** Mergeable alone: v8 unknown sends stay `interrupted`, blocked and visible.
- Contents:
  - version gate and refusals;
  - interruption record;
  - exclusive claim;
  - unconsumed-grant release and regrant;
  - evidence reuse and drift check;
  - `runtime_outcome_recorded` and the pre-seal seam;
  - `recovery` receipt block and validator;
  - sealed digest;
  - ledger-backed lead guard;
  - `superseded` seal;
  - `predecessors`;
  - inspection.
- Covers: AC1, AC2, AC3, AC4 (b, d, f, g, h, i, transport), AC6, AC7, AC8, AC9, AC10 (generation and marker subtests), AC11, AC12 (test-runner mutation check).

**Chunk 2: continuation after operator resolution.**
- Contents:
  - `manager_call_resolutions`;
  - operator response import for actions (v5 precedent) and for manager calls;
  - binding check at continuation;
  - receipt resolution list.
- Covers: AC4 (a, c, e), AC5, AC8 (no-dispatch regrant), AC10 (added and removed resolution subtests), AC12 (worker-adapter mutation check).

## Owned risks

| Risk | Owner | Mitigation |
|---|---|---|
| R1. Restore when no checkpoint is bound (first-action (b) before G:904) | lead-developer | Spike in planning. If no bound checkpoint exists, fail closed with `no_restorable_checkpoint`. No from-scratch replay unless the manager `call_id` and `prompt_digest` are proven deterministic. |
| R2. Receipt-only validation cannot see a removed resolution | test-engineer | Cross-check against action reasons (`operator_resolved_*`, `recovery_*`). Also check the ledger-side `sealed_receipt_sha256` in `inspect-delivery`. |
| R3. A truly lost response has no observation, so it cannot be resolved | engineer | Chunk 2 accepts operator-supplied responses that pass the `observe_*` validation. Otherwise it stays blocked and abandon stays available (ADR 0012 Consequences). |
| R4. A successor attempt resets the per-attempt limits | engineer (decision) | Count predecessors' paid and verifier sends from `predecessors` in `decide`. |
| R5. `resolve-execution` routes to `execution_gateway.resolve_attempt`, whose v8 support is unverified (I) | lead-developer | Verify it in chunk 2 and add a v8 route if missing. |
| R6. The C:239 guard depends on the ledger being readable | sre | A read-only ledger open. Fail closed if it is unreadable. |

## ADR 0016 outline (references ADR 0012, 0013, and 0014)

- **Decision:**
  - v8 attempts gain a non-terminal "interrupted, recoverable" state, with no receipt.
  - Recovery continues the same attempt under a new ledger fence.
  - Exactly one receipt is sealed, carrying the recovery facts.
  - Uncertain sends are never resent and never produce a terminal `unknown` for v8.
- **Amendment to ADR 0014:**
  - A lead resume or supersede seals the in-flight attempt as `superseded`.
  - The successor starts a new attempt from the charter baseline, linked through `predecessors`.
  - Ledger uncertainty blocks a lead change. Abandon stays available.
- **Consequences:**
  - v5 epochs (ADR 0013) stay v5-only. v6 and v7 are unchanged.
  - Inspection must explain the interrupted state.
  - Limits are counted across the lineage.
  - Adoption under a successor generation stays possible later, as an additive link.
- **Alternatives:** Option B and Option C, with the reasons given above.

## Dispositions for the definition's open questions

1. **Recovery shape:** same-attempt resume only (Option A). The continuation epoch is rejected for v8.
2. **A second attempt:** yes. It is created only after a lead resume or supersede and only once every sibling attempt is terminal. It starts from the charter baseline in a fresh worktree, and G:344-366 already enforces that baseline (O).
3. **The interruption marker:** a ledger `attempt_interruptions` row (cause is transport, reconciliation required, or unmarked process exit). The ledger status stays `started`. There is no `interruption.json` for v8. The record informs; it never authorizes.
4. **The pre-seal seam:** a keyword-only `seal_hook(point)` on `_execute_prepared_delivery`, in the style of C:171 `failure_point`, not exposed on the CLI. Its points are `after-runtime-outcome`, `after-receipt-draft`, and `before-finish-attempt`. Tests raise at each point, recover, and assert one sealed receipt and zero sends.
