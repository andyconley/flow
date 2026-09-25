# Plan: Shaper expansion approval (MAF adoption step 5, slice 1)

- **Status:** shape accepted by the engineer on 2026-09-25 (they invoked `/flow-implement` in response to the Phase 2 shape).
- **Inputs:**
  - approved `requirements.md` and `acceptance-criteria.md` (AC1–AC12);
  - `solution.md` (Option A, replay under a grant, one pass);
  - `adversarial-review.md` (E1–E4);
  - `research/resume-mechanics-spike.md`.
- **Plan engagement decisions (2026-09-25):**
  - 1a: plan reviewers are architecture (architect) and validation (test-engineer) only.
  - 2a: independent quality and security reviews run before handback.
  - 3a: stay on `codex/step5-shaper-approval-design`, one PR.
  - 4a: the runner ceilings live in a dependency-free module under `runtime/maf_runner/`, imported by `cli/`.
- **Plan review:** `plan-review.md` (A1–A12, T1–T6), plus engineer decisions E5 (a) and E6 (a). The section **Amendments from plan review** at the end is binding, and supersedes any conflicting text above it.

## Problem

A chartered v8 Delivery Lead is denied outright when it hits a charter limit. The fix works in three steps:

1. Flow records a request that Flow itself computes.
2. It grants the request automatically within sealed lineage headroom, or pauses the attempt for Andy's decision.
3. On resume, it replays the *exact* denied proposal under a single-use grant. The envelope and charter never change.

## Desired outcome

One implementation pass that meets AC1–AC12 on protocol v8. Protocols v5–v7 are untouched. The full suite passes with 0 failures and 0 skipped, with `FLOW_MAF_PYTHON` set.

## Scope

- **In scope:**
  - charter headroom and ceilings;
  - the ledger request and grant tables;
  - inline automatic approval;
  - the `expansion_paused` stop path;
  - `decide-expansion`;
  - recovery replay for worker, manager and restart cases;
  - visibility in status, list and inspect;
  - receipt fields and validation;
  - ADR 0017;
  - a MAF-gated end-to-end test;
  - the AC12 mutation checks.
- **Out of scope:**
  - the definition's non-goals: replan expansion (E1), the optional specialist pool (E2), a model recommendation, a token cap, MCP, re-sealing the charter, live provider runs, a cross-project inbox and usage metrics;
  - refactoring limit code that expansion doesn't need.

## Resolved design facts (from current-state inspection)

- **Pause signal.**
  - A new `ExpansionPaused(Exception)` in `cli/delivery_gateway.py`, raised from the `on_action` and `on_manager` callbacks when the ledger returns `reason == "expansion_pending"`.
  - The supervisor kills the child and re-raises. `_run_prepared_delivery`'s existing `except Exception` (about `delivery_gateway.py:1485`) gets a branch *before* the interruption and runtime-outcome routing. The branch calls `ledger.record_expansion_pause(...)` and returns `{"status": "expansion_paused", "request_id": …}`.
  - Nothing is in flight at that point, so killing the child loses nothing.
- **Truly paused** means all of the following:
  - `ledger.recovery_lock(attempt_id, holder="decide")` can be acquired (a running attempt holds `holder="live"`, `delivery_gateway.py:1259`);
  - no `actions` or `manager_calls` row is `started` or `unknown`;
  - the attempt has an expansion-pause marker whose request is `pending`.
- **Lineage** is the run's v8 attempt chain: `envelope["predecessors"]` plus the current attempt. This matches `_lineage_usage` (`execution_ledger.py:335`). `lineage_id` is the first attempt's ID.
- **Ceilings.**
  - A new file, `runtime/maf_runner/limits.py`, with no imports beyond the standard library:
    - `MAX_MANAGER_CALLS = 12`;
    - `MAX_MANAGER_ROUNDS = 6`;
    - `MAX_ACTIONS = 6`, which also bounds delegations and paid worker calls;
    - `MAX_VERIFIER_CALLS = 2`;
    - `MAX_RESETS = 2`.
  - The runner imports it as `runtime.maf_runner.limits`.
  - `cli/` loads it by file path: `importlib.util.spec_from_file_location` on `Path(__file__).resolve().parents[1] / "runtime/maf_runner/limits.py"`. The `cli` modules don't have the repo root on `sys.path`, and the release layout `~/.flow/source/runtime/maf_runner/` is present.
  - A small `cli/runner_limits.py` shim exposes the constants to `cli/` code, so there is only one loader.
- **`delegated_expansion`** is derived: it must equal `any(headroom.values()) > 0`. Existing intents, with no headroom and `false`, stay valid.
- **Test fixture.** `tests/shaper_intent_fixture.py` sets its base limits *at* the ceilings. It gains an optional parameter for headroom and lowered base limits; the default is unchanged.
- **The orchestration manifest** is sealed into the delivery authority (`delivery_control.start_plan` compares `source_digests`), so it is *not* edited. Plan and implement reviewer dispatches are recorded in the run artifacts. The gap is recorded at archive.

## File-level change plan (ordered commits)

Each commit is Conventional Commits, and the fail-closed suite (`scratchpad/suite-main.sh`) runs before each one.

### C1 `feat(contracts): seal delegated expansion headroom in the charter`

- `runtime/maf_runner/limits.py` (new): the constants listed above.
- `runtime/maf_runner/delivery_lead.py`: replace the literals 12, 6 and 2 (`manager_call > 12`, `manager_round > 6`, `action_number > 6`, and `StandardMagenticManager(max_reset_count=2, max_round_count=6)`), plus the resume validation of `manager_calls_committed` and `replans_committed`, with the constants.
- `cli/runner_limits.py` (new): the path-based loader.
- `cli/delivery_contracts.py`:
  - `validate_shaper_intent` (about line 100) accepts an optional `expansion_headroom` mapping over `{delegations, paid_worker_calls, verifier_calls, manager_calls, manager_rounds}` to non-negative non-bool ints, and rejects unknown keys (replans and concurrency included);
  - the `delegated_expansion is not False` check (lines 128 and 260) becomes "equals derived";
  - a ceiling check is added: base + headroom ≤ the ceiling for each limit, and verifier total ≤ 2.
- `build_shaper_contract` and `build_delivery_charter` seal `limits.expansion_headroom`, zeros by default.
- `docs/adr/0017-delegated-expansion-headroom.md` (new):
  - the decision;
  - lineage scope;
  - replay under a grant;
  - the state diagram `started → expansion_paused → decided → recovered`;
  - it supersedes the disabled-expansion rule in ADR 0014.
- Tests:
  - `tests/test_shaper_delivery_contracts.py`, for AC1 (sealing, refusals, derived flag);
  - `tests/shaper_intent_fixture.py` (optional parameter);
  - update the `delegated_expansion` assertions in `tests/test_chartered_delivery_gateway.py` and `tests/test_expertise_composition.py` where they asserted a forced `false`.

### C2 `feat(ledger): record expansion requests and grant within headroom`

- `cli/execution_ledger.py`:
  - **Schema:** tables `expansion_requests` and `expansion_grants`, as in `solution.md`, with `UNIQUE(attempt_id, kind, denied_row_id)`. `request_id = "exp-" + sha256(attempt|kind|row)[:24]`.
  - **`_effective_limit(db, envelope, name)`:** the sealed base plus the approved grants across the lineage. It is used by the five limit checks in `decide` (about line 657) and `decide_manager_call` (about line 851) in place of direct `envelope["limits"][…]` reads. The headroom map is read from the sealed charter only, and prepare loads it into the envelope under a charter-derived key that is covered by the envelope digest check.
  - **Denial hook**, v8 only, for expandable reasons only, in the same `BEGIN IMMEDIATE`:
    1. Upsert the request.
    2. If `headroom_remaining(lineage, name) ≥ 1` and effective + 1 ≤ the ceiling, record an automatic grant, consume it, and return allowed with a normal provider grant; no denied row is written.
    3. Otherwise write the denied row as today and return `{"allowed": False, "reason": "expansion_pending", "request_id"}`.

    Replaying the same denied row returns the existing request and decision.
  - **Hard denials** (`provider_denied`, `specialist_denied`, `concurrency_cap`, `verifier_retry_denied`, `producer_already_completed`, a scope violation, a prohibited capability, replan) never create a request.
  - **Snapshot and read helpers:** `expansion_requests(attempt_id)`, `lineage_expansion(envelope)`.
- Tests in `tests/test_execution_ledger.py` or a new `tests/test_expansion_ledger.py`:
  - AC2: a request per limit, amount 1;
  - AC3: hard denials;
  - AC4: automatic approval, exhaustion then escalation, idempotent replay, and the crash window drawing headroom once;
  - AC8: lineage inheritance, not refilled;
  - AC11: v5–v7 unchanged.

### C3 `feat(gateway): pause chartered delivery on escalated expansion`

- `cli/delivery_gateway.py`:
  - **`ExpansionPaused`.**
  - **Worker path:** before raising, bind the proposal's checkpoint with `pending_kind=worker`. Today it is bound only when allowed (about line 1413), and the new binding reuses the same helper.
  - **Manager path:** raise with no binding.
  - **The catch branch** in `_run_prepared_delivery`, which returns the `expansion_paused` status.
- `cli/execution_ledger.py`: `record_expansion_pause(attempt_id, request_id, *, generation)`. It is a new `attempt_expansion_pauses` table, or a column; it is distinct from `attempt_interruptions`, and the attempt row stays `started`.
- `cli/delivery_projection.py` and `cli/runstate.py`:
  - `flow run status` and `flow run list` show `next_action: decide expansion <request_id>`;
  - `inspect-delivery` shows request rows with the limit, the headroom left, the grants and the escaped rationale.
- Tests:
  - AC2: pausing before send, claim active at the same generation, visibility;
  - the rationale escaping and manager-supplied amounts being ignored (part of AC10).

### C4 `feat(cli): add flow run decide-expansion`

- `cli/delivery_gateway.py` `decide_expansion(work_id, attempt_id, request_id, *, approve, expected_generation, actor, explanation, root)`:
  - **Lock order:** recovery (`holder="decide"`), then run, then send, then SQLite `BEGIN IMMEDIATE`.
  - **Refusals, with no changes made:**
    - `stale_generation`;
    - `unknown_request`;
    - `expansion_already_decided`;
    - `attempt_not_paused` (a started or unknown row, or the lock is held);
    - `ceiling_exceeded`, including the verifier ceiling of 2.
  - A manual grant has `authority=engineer` and doesn't draw headroom.
- `cli/flow.py`: the subcommand `flow run decide-expansion <work> <attempt> <request> (--approve|--deny) --expected-generation N --actor A --explanation E [--json]`.
- Tests in `tests/test_expansion_decide.py`:
  - AC5, all refusals;
  - AC10: two concurrent decisions produce one winner and one `expansion_already_decided`; deciding against a supersede produces one outcome.

### C5 `feat(recovery): resume expansion pauses by replaying under the grant`

- `cli/delivery_recovery.py` `recovery_eligibility` (line 116):
  - an expansion pause with a pending request returns `expansion_decision_required`;
  - a decided worker pause gets `pending` mode on the bound denial checkpoint;
  - a decided manager pause gets `answer` or `pending` from the latest bound worker checkpoint, or `restart` when none exists and every prior manager call is completed.
- `cli/delivery_gateway.py`:
  - `_resume_chartered` (line 671) supports `restart`: a fresh `start` message on the byte-identical envelope, with the same `checkpoint_dir`;
  - completed manager calls replay through `duplicate_manager_request`.
- `cli/execution_ledger.py`: `regrant_expanded_action` and `reissue_expanded_manager_grant`, modelled on lines 538 and 607.
  - The replayed denied row plus an unconsumed approved grant is allowed once, and sets `consumed_by` atomically.
  - A second replay gets `expansion_grant_consumed`.
  - A replay under a deny returns the denial, which is reported to the manager.
  - The denied row is marked superseded by the grant, never rewritten.
- Supersede and release paths: pending requests are marked `cancelled` in the same transaction.
- Tests:
  - AC6: resume after approval, no re-send, single consumption;
  - AC7: resume after denial, a new request on re-proposal;
  - AC8: cancellation.

### C6 `feat(receipts): record and verify expansion requests and grants`

- `cli/execution_contracts.py` and the receipt assembly in `cli/delivery_gateway.py`:
  - the receipt fields `expansion_requests` and `expansion_grants`, in ledger order;
  - validation recomputes effective limits and headroom in order.
- Validation rejects:
  - a grant that was added, removed or altered;
  - automatic spending beyond the headroom;
  - the wrong authority;
  - an amount above 1;
  - a grant tied to another lineage or generation.
- Tests: AC9.

### C7 `test(maf): prove expansion replay end to end`

- `tests/test_maf_expansion.py` (new), MAF-gated through `FLOW_MAF_PYTHON`:
  - automatic approval;
  - a worker escalation: approve, resume, complete;
  - a manager escalation: deny, resume, complete;
  - a manager escalation before any checkpoint: restart;
  - a `call_id` replay regression assertion, which covers the MAF-pin risk.
- The AC12 mutation checks are recorded in `validation-results.md`.
- `docs/maf-adoption-design.md` status table: step 5, slice 1 shipped (pending merge).

## Contracts

- **Data:** the two new tables plus the pause marker, all additive. The receipt gains two ordered arrays. The charter gains `limits.expansion_headroom`.
- **Workflow:**
  - `started → expansion_paused (request pending) → decided (granted|denied) → recover → started`, then completes or pauses again;
  - supersede or release cancels pending requests;
  - every write is generation-fenced and done in one `BEGIN IMMEDIATE`.
- **CLI:** `flow run decide-expansion …` as above. `status`, `list` and `inspect-delivery` show new fields.

## Risks

These are owned by Andy, as in `solution.md`: MAF replay identity (a regression test), the widened checkpoint lifecycle, the new restart mode, and the size of a one-pass change.

- **New:** the path-based import of `limits.py` could break if the release layout changes.
  - Mitigation: a test asserts that `cli/runner_limits.py` and `runtime.maf_runner.limits` resolve to the same file and the same values.

## Amendments from plan review (binding)

### Acceptance-criteria amendments (engineer-approved 2026-09-25)

The sealed AC file is not edited, because it is part of the delivery authority. These amendments govern instead.

- **AC6 (A8).** A granted replay changes the denied row from `denied` to `allowed` with reason `expansion_granted`. The original denial is kept in events and in the request row. "Not rewritten" means the denial record is never lost.
- **AC7 (E5 a).**
  - Deny-and-continue applies to **worker** denials.
  - A denied **manager** call seals the attempt `failed` with reason = the limit, through the existing seal mode, and Flow never writes manager text.
  - The end-to-end case 3 becomes two cases: "manager escalation, approve, resume, complete" and "manager escalation, deny, sealed `failed`".
- **AC8 (E6 a).**
  - Headroom is one lineage-wide pool, never refilled (E3 holds).
  - A consumed grant raises only the counter it applies to: across the lineage for `paid_worker_calls` and `verifier_calls`; for its own attempt for `delegations`, `manager_calls` and `manager_rounds`.
  - Approved grants a superseded attempt never used become `lapsed`.
  - A successor inherits the remaining headroom and the lineage-counter grants.

### Design amendments

- **Ceilings everywhere (A1).** In C1, the v8 supervisor guards (`cli/maf_supervisor.py:473-489`) are bounded by `runner_limits` ceilings, not base + 1. A regression test goes in C7.
- **Evaluate every predicate (A3).** `decide` and `decide_manager_call` evaluate every predicate. Expansion applies only when no hard predicate fails: producer completed, verifier retry, concurrency, provider or specialist, scope, capability, replan not authorized or out of order. The request stores `limits: [...]`, the full set of failing expandable limits, one unit each. Automatic approval requires headroom for all of them. A manual grant covers the set. Keying stays `UNIQUE(attempt_id, kind, denied_row_id)`.
- **One limit reader (A5).** `_effective_limit` replaces every limit read: `_v8_limit_reason` (`execution_ledger.py:573-605`) and `:1170` in C2; `execution_contracts.py:378-379`, `:901` and `:971-974` in C6.
- **Pause marker = pending request row (A6).**
  - There is no separate pause table. The pending request is written in the denial transaction.
  - `bind_magentic_checkpoint` (`:1575`) accepts a denied row only when it has a pending expansion request.
  - `claim_chartered_recovery` (`:482`) accepts `restart`, and skips the `unmarked_process_exit` write (`:514-518`) for expansion pauses.
  - A worker pause whose checkpoint was never bound refuses with `reconciliation_required`.
- **Recovery positions (A7).**
  - A manager pause after a worker denial resumes in `answer` mode with the recorded denial reply.
  - `restart` requires the attempt to have zero action rows and every prior manager call `completed`.
- **Suite stays green per commit (A9).** In C2 the ledger keeps `reason=<limit>` and adds `expansion: {request_id, status, limits}`. The gateway starts acting on it in C3.
- **Lock holder (A10).** `recovery_lock` gains holder `decide`. A decision against a held lock refuses with `attempt_not_paused`.
- **Envelope placement (A11).**
  - `expansion_headroom` is a top-level v8 envelope key, projected at prepare (`delivery_gateway.py:451-461`) from the canonical charter.
  - `validate_envelope` (`execution_contracts.py:249`) and `validate_delivery_charter` (`delivery_contracts.py:301-304`) are updated.
  - A consistency rule is added: paid headroom ≤ delegation headroom when paid base ≤ delegations base.
- **Cancellation earlier (A12).** Cancelling pending requests and lapsing unused grants on supersede or release (in `seal_superseded_attempts`, `:409-437`) moves to C4.

### Validation amendments

T1–T6 are reflected in `validation-plan.md`.

## Next lane

`flow-implement`.
