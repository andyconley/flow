# Solution: Shaper expansion approval (MAF adoption step 5, slice 1)

- **Status:** accepted by the engineer on 2026-09-25. Option A, delivered in **one pass**.
- **Inputs:**
  - `requirements.md` and `acceptance-criteria.md` (approved);
  - `adversarial-review.md`;
  - `research/resume-mechanics-spike.md`.
- **Archive search:** selection `a298c4f7f11b…`, complete, 17 matches. Adapted precedents:
  - chunk 1a: resume from the latest bound checkpoint, including `pending` mode;
  - `maf-post-resolution-continuation`: restore the exact pending checkpoint before continuing;
  - chunk 2: operator decision, then `recover-delivery-lead`.

  No retrieved decision conflicts, apart from the disabled-expansion rule, which the approved definition supersedes.

## Definition amendments made in solutioning (engineer-approved)

- **Inline automatic approval.** This refines R3 and R4. A request within headroom is granted in the same ledger transaction that records it, and the attempt carries on with no pause. Only escalated requests pause the attempt. Request keying, headroom accounting, receipts and fencing are unchanged.
- **All five limits in one slice.** Delegations, paid calls, verifier calls, manager calls and manager rounds, as approved. The engineer declined to split manager limits into their own slice.
- **Deciding and resuming are separate commands.** `decide-expansion`, then `recover-delivery-lead`.

## Problem

A chartered v8 Delivery Lead that hits a charter limit is denied outright. The fix records a Flow-computed request, grants it automatically within sealed headroom, or pauses the attempt for Andy's decision. Resuming brings back the *exact* denied proposal under a grant, and neither the envelope nor the charter changes.

## Applicable rules

- **`standards/architecture.md`, Layering / Domain and integration boundaries:** MAF stays behind the gateway, and authority lives in Flow's ledger and sealed artifacts, never in checkpoints.
- **`standards/orchestration.md`, Claim provenance and reconciliation / Lifecycle enforcement:** grants are Flow-authored claims with an owner and evidence, and stage gates recheck them.
- **ADR 0011 and 0012:** Flow-owned authority and evidence. Manager output is untrusted and display-only.
- **ADR 0014:** the sealed charter plus `run.json` are the authority chain, and every boundary is generation-fenced.
- **ADR 0015:** the verifier ceiling is 2.
- **ADR 0016:** the lock order is recovery, then run, then send, then SQLite. Resume only from bound state; operator reconcile then recover.

## Options

- **Option A, replay under a grant (chosen).**
  - Shape: pause cleanly at an escalated denial. Resume through existing recovery modes, so the denied proposal replays under its original ID, and an unconsumed expansion grant allows it.
  - Pros:
    - reuses `pending` mode, `regrant_recovered_action`, `reissue_recovered_manager_grant`, and ledger replay of completed calls;
    - the envelope and charter are immutable;
    - Magentic never has to propose again.
  - Cons: a checkpoint must be bound at denial; replay identity depends on the pinned MAF version; a new fresh-restart mode is needed.
  - Reversibility: medium, because the new tables and states are additive.
- **Option B, hold the child in-process** while waiting.
  - Pros: simplest.
  - Cons: violates D3, holds a long-lived process and locks, and a crash loses the wait.
  - Rejected.
- **Option C, a successor attempt with raised limits.**
  - Cons: the envelope changes, so no `call_id` replays; work is re-sent; it amounts to re-sealing the charter.
  - Rejected.

## Recommendation: Option A

### Contract

- **Intent.** `validate_shaper_intent` accepts optional `expansion_headroom`, a mapping over `{delegations, paid_worker_calls, verifier_calls, manager_calls, manager_rounds}` to non-negative integers. It defaults to all zeros.
  - `delegation_matrix.delegated_expansion` becomes derived. It is true exactly when any headroom is greater than zero, and the check that forced it to `false` is removed.
  - Replans and concurrency are rejected as unknown keys.
- **Sealing** (`build_shaper_contract` and `build_delivery_charter`). The charter seals `limits.expansion_headroom`. Validation refuses any base + headroom above the runner ceilings: 12 manager calls, 6 manager rounds, 6 delegations or actions, and 2 verifier calls.
  - The ceilings live as named constants in one module, imported by both the contract validation and the runner, so they cannot drift.
- **Headroom source.** Automatic approval reads headroom only from the sealed charter artifact, which prepare already loads as the authority, and never from envelope or manager fields.

### Ledger (`cli/execution_ledger.py`)

- **New table `expansion_requests`:** `request_id`, `lineage_id`, `attempt_id`, `owner_generation`, `kind` (`delegate` or `manager_call`), `denied_row_id` (an `action_id` or `call_id`), `limit_name`, `amount` = 1, `proposal_digest`, `rationale` (bounded, display-only), `evidence_digests`, `status` (`pending`, `granted`, `denied` or `cancelled`), and `created_at`.
  - `UNIQUE(attempt_id, kind, denied_row_id)`. `request_id` is derived deterministically from that key.
- **New table `expansion_grants`:**
  - `grant_id` and `request_id` (unique);
  - `authority`: `charter_headroom` or `engineer`;
  - `actor` and `explanation`, for a manual decision;
  - `decision`: `approve` or `deny`;
  - `amount`, `owner_generation`, `decided_at`;
  - `consumed_by`, which is null until one allowed decision consumes it.
- **Denial hook.** `decide` and `decide_manager_call` are unchanged until they produce an expandable denial reason. Then, in the same `BEGIN IMMEDIATE` transaction:
  1. Insert the request, or return the existing one for a replay.
  2. Compute the lineage's remaining headroom as sealed headroom minus automatic grants across the lineage. If that is at least 1, and the effective limit plus 1 stays within the ceilings, record an automatic grant, consume it immediately, and return **allowed** with a fresh provider grant. The denied row is never written: the action row is inserted as allowed, and the grant links to it.
  3. Otherwise return `{"allowed": False, "reason": "expansion_pending", "request_id": …}`, and store the denied row as today with `reason = <limit>`.
- **Effective limits.** Sealed base plus approved grants across the lineage. This replaces direct reads of `envelope["limits"][...]` in the five limit checks, through one helper, `_effective_limit(db, envelope, name)`.
- **Replay under a grant.**
  - A replayed denied row with an unconsumed approved grant is allowed once, through the new `regrant_expanded_action` and `reissue_expanded_manager_grant`. These are modelled on the existing regrant and reissue functions.
  - The grant's `consumed_by` is set atomically. A second replay gets `expansion_grant_consumed`.
  - A replay under a denied decision returns the denial, and the gateway reports it to the manager.
- **Hard denials.** `provider_denied`, `specialist_denied`, `concurrency_cap`, `verifier_retry_denied`, `producer_already_completed`, a scope violation, a prohibited capability, and v8 replans never create requests.
- **Lineage.** `lineage_id` is the first attempt's ID, carried through supersede. That is the same basis as today's predecessor counting for paid calls and verifier calls.

### Gateway and runner (`cli/delivery_gateway.py`, `runtime/maf_runner/delivery_lead.py`)

- **Worker `expansion_pending`.**
  - Bind the proposal's checkpoint with `pending_kind=worker` before replying.
  - Record an `expansion_pause` marker, a new attempt state distinct from `record_interruption` and the runtime outcome.
  - Tell the supervisor to stop the child cleanly.
- **Manager `expansion_pending`.** The same, with no new checkpoint. Resume uses the latest bound worker checkpoint, or a fresh restart if none exists.
- **Attempt and claim state.** The attempt stays open (`started`, with the pause marker). The lead claim stays `active` at the same generation.
- **The runner ceilings** come from the shared constants module.

### Decide

- **Command:** `flow run decide-expansion <work> <attempt> <request> --approve|--deny --expected-generation N --actor … --explanation …`.
- **Locks:** it takes the recovery, run and send locks, then a SQLite `BEGIN IMMEDIATE`.
- **Refusals** (no changes made):
  - a stale generation;
  - an unknown or already-decided request (`expansion_already_decided`);
  - a request that isn't pending;
  - an attempt that isn't truly paused: an action or manager call is `started` or `unknown`, the recovery lock is held, or a live supervisor PID is recorded;
  - a grant that would go above a ceiling or the verifier ceiling of 2.
- Manual grants never touch headroom.

### Recovery (`cli/delivery_recovery.py` and `resume_delivery`)

- **Eligibility.** When the attempt has an expansion pause whose request is decided:
  - **Worker:** `pending` mode on the denied action's checkpoint.
  - **Manager:** `answer` or `pending` mode from the latest worker checkpoint. If there is none, the new mode `restart` launches the child with a fresh `start` message on the identical envelope.
  - Completed manager calls replay from the ledger through the existing `duplicate_manager_request` path, and the denied `call_id` is then allowed under the grant.
- **A pause whose request is still pending** refuses with `expansion_decision_required`.
- **Supersede or release** with a pending request marks it `cancelled` in the same transaction.

### Visibility and evidence

- `flow run status` and `flow run list` show `next_action: decide expansion <request_id>`.
- `inspect-delivery` shows each request: the limit, the headroom left, the grants, and the rationale, escaped.
- Receipts gain `expansion_requests` and `expansion_grants`. Receipt validation recomputes effective limits and headroom in order, and rejects:
  - a grant that was added, removed or altered;
  - automatic spending beyond the headroom;
  - a grant under the wrong authority;
  - an amount above 1;
  - a grant tied to another lineage or generation.

## Session Model Advice

- **Coordinator recommendation:** the judgment profile (`claude-opus-4-8`, high effort). This changes who holds authority over provider calls.
- **Active parent:** unknown; Flow could not verify it.
- **Effective delegated assignments:** reviewers per the manifest.
- **Switch performed:** no.

## Delivery: one pass, with an ordered commit sequence

1. The shared ceilings module, plus intent, contract and charter headroom, with sealing validation and tests. ADR 0017.
2. The ledger tables, request keying, effective limits, inline automatic approval, hard-denial classification, and tests.
3. The gateway pause path (worker checkpoint binding, manager pause), the pause marker, and status, list and inspect display.
4. `decide-expansion`, with its locks and guards.
5. Recovery modes: expansion-aware `pending` and `answer`, the new `restart` mode, grant-consuming replay, and lineage handling of pending requests.
6. Receipt fields and validation.
7. A MAF-gated end-to-end test covering an automatic approval, a worker escalation (approve, resume, complete), a manager escalation (deny, resume, complete), and a pre-checkpoint manager escalation (restart), plus the mutation checks in AC12.

## Risks (owned)

- **Manager replay identity depends on the pinned MAF version.** Owner: Andy. Mitigation: a MAF-gated regression test asserting identical `call_id` replay, which runs on every change to the MAF pin.
- **Binding a checkpoint at denial widens the checkpoint lifecycle.** Owner: Andy. Mitigation: a checkpoint bound at denial is only usable with an approved grant, and recovery treats it as a pending position only. Existing quarantine rules apply to unbound checkpoints.
- **The fresh-restart mode is new.** Owner: Andy. Mitigation: it is allowed only for a manager expansion pause with no worker checkpoint, requires every prior manager call to be completed and replayable, and refuses on any identity mismatch.
- **One pass means a large change.** Owner: Andy. Mitigation: the ordered commits, a fail-closed suite run before each commit, and independent quality and security review before handback.

## Suggested design artifacts

- **ADR 0017:** delegated expansion under sealed headroom. It supersedes the disabled-expansion rule from ADR 0014 and `shaper-delivery-runtime-contracts`.
- **A state diagram** in ADR 0017: `started`, then `expansion_paused`, then decided, then recovered.
- The spike, already recorded in `research/resume-mechanics-spike.md`.

## Next lane

`flow-plan`. It shapes the single pass into file-level steps, the validation plan and the orchestration assignments.
