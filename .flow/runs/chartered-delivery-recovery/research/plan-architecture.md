# Plan architecture: chartered v8 delivery recovery (chunk 1 design, R1 spike)

- Role: architect. Date: 2026-09-23. Run `chartered-delivery-recovery`, lane `plan`. Base `main` at `9436527`. Everything here was read-only; this file is the only output.
- Abbreviations: G = `cli/delivery_gateway.py`, L = `cli/execution_ledger.py`, X = `cli/execution_contracts.py`, C = `cli/delivery_control.py`, P = `cli/delivery_projection.py`, EG = `cli/execution_gateway.py`, S = `cli/maf_supervisor.py`, RN = `runtime/maf_runner/delivery_lead.py`, F = `cli/flow.py`.
- Claim markers: **[O]** observed in code at the cited line, **[I]** inferred from the cited code, **[R]** recommended, **[U]** unverified.
- Line numbers were re-read on this base. Some line numbers in `research/solution-options.md` and `research/recovery-boundary.md` came from the pre-merge worktree. Where they differ, the anchors here win.

---

## 0. Findings that change or sharpen the accepted solution

Read these first. None of them reopens Option A, but four of them add work to chunk 1 that `solution.md` did not list.

1. **The MAF runner cannot restore at an unanswered pending action. [O]** The restore path needs `resume.result` and always answers the pending request (RN:289, RN:296-297). Boundary (b) needs a new runner mode that re-emits the saved proposal with its original `checkpoint_id` without answering it. (b) is an unconsumed grant on an action whose checkpoint *is* bound. Restoring from an earlier checkpoint instead cannot work: MAF re-proposes the action with a new checkpoint id, so the action id changes (X:406-412), and `decide` then refuses with "logical action slot already occupied" (L:331-336). **This contradicts the requirements assumption "No runtime work is needed."** [R] Add a `pending` resume mode to RN (§2, item 4).
2. **Stale unbound checkpoint files can turn a recovery into a sealed `failed`. [I]** After an answer-mode restore, the runner looks for checkpoints that hold the next pending request id and aborts if it finds more than one (RN:306-309). Suppose the crashed run had MAF write a pending checkpoint for action k+1 before Flow recorded a decision. The restored run then finds two such files, raises `PolicyAbort`, Flow sees `MafChildError`, and the attempt would be sealed `failed`. Nothing is resent, but the outcome is wrong. [R] Before restoring, move every checkpoint file that the ledger has not bound into `checkpoints-quarantine/<recovery_id>/`, and record their digests (§2, item 4). [I] The same hazard exists in today's v5 `resume_delivery`.
3. **The ledger fence generation and the lead generation diverge after any recovery claim. [O]** `create_attempt` seeds `owner_generation` from the lead claim (L:240-243). `_claim_recovery_locked` then increments it (L:265-266). `inspect_delivery_projection` computes `active` as `ledger owner_generation == envelope claim generation` (P:36), so every recovered attempt would show as not executable. [R] Inspection must compare the envelope's claim against `run.json` (the `delivery_authority_guard` rule, C:49-54), not against the ledger fence.
4. **Allowed-but-unconsumed manager grants are not covered. [O]** A replayed `decide_manager_call` returns the stale `grant_id` (L:509-516). `consume_manager_grant` then expires it and turns the row `denied/grant_expired` (L:565-569), and the gateway raises (G:813-814). A crash between G:802 and G:813 therefore breaks every restore that replays that manager call. [R] Re-issue the grant in place when replaying under recovery (§2, item 6).
5. **A regrant must refresh the grant clock that expiry reads. [O]** `consume_grant` and `prepare_verifier_send` measure expiry from the latest `policy_allowed` event only (L:617, L:645). `regrant_not_dispatched` writes `policy_reallowed` (L:970), and expiry does not read that event. [R] The v8 regrant writes a fresh `policy_allowed` event with detail `recovery_regranted`. The expiry lookups stay unchanged, so v5-v7 behave exactly as before.
6. **Simulated kills must bypass `except Exception`. [O]** G:909-912 closes an unconsumed grant as `not_dispatched/pre_send_failure` on any `Exception`. G:953-956 marks the action unknown, and G:979 turns any `Exception` into a sealed receipt. A test that raises `RuntimeError` at a kill point therefore exercises a different state from a process death. [R] Kill tests and `seal_hook` points raise a `BaseException` subclass (for example `KillPoint(BaseException)`).
7. **An existing test's expected outcome flips. [O]** `test_v7_transport_loss_after_producer_seals_nonresumable_receipt` (`tests/test_chartered_delivery_gateway.py:725-755`) runs through `execute_chartered_delivery`, which now always mints v8 (G:387). It asserts a sealed `failed` receipt after `MafTransportError`. Under design item 2 that becomes `interrupted` with no receipt. The test must be renamed and inverted in the commit that changes the behavior. The flip is intended; it is not a regression.
8. **Opening the ledger for writing runs schema DDL. [O]** The constructor runs `executescript` and `ALTER`s (L:53-187), so the ledger file changes the first time it is opened after an upgrade. [R] Refusal gates must open the ledger with `read_only=True` (L:37-43, L:190). That makes AC1's before-and-after snapshot hold byte for byte.

---

## 1. Spike R1: replay without a bound checkpoint

**Question.** A v8 attempt was interrupted before any Magentic checkpoint was bound. Can it be replayed safely from the charter baseline? "Safely" means no provider resend, no duplicate grant, and no ledger row whose meaning changes.

### 1.1 What can exist before the first bind

Checkpoint binding happens only in `on_action`, after `decide` and before the grant is consumed (G:857-858, then G:903-905, then G:906-908) [O]. `bind_magentic_checkpoint` is called from exactly one place, with `pending_kind="worker"` (G:904) [O]. Manager calls are never bound [O]. The unbound states are therefore:

| # | Ledger state at interruption | Evidence |
|---|---|---|
| U0 | Attempt `started`. No manager-call rows and no action rows. | `create_attempt` writes one row and one event (L:243-244) [O] |
| U1 | Manager calls `completed` only. No action rows. | `observe_manager_response` (L:595) [O] |
| U2 | Manager call `allowed`, grant not consumed. | Gap between G:802 and G:813 [O] |
| U3 | Manager call `started` (sent, no response). | L:570 [O] |
| U4 | First action `allowed`. The checkpoint file exists (G:900-902) but is **not bound**. | Gap between L:444 and G:904 [O] |
| U5 | Later action k+1 `allowed` but unbound, while action k is bound. This generalizes R1: the **latest** proposed action has no bound checkpoint. | Same code path [I] |

### 1.2 What a replay from the baseline would do

A replay means starting MAF again with `type: start` (S:467, RN:261-262) on the same attempt, envelope, and task.

- **Resend (U3).** Any recovery claim turns `started` into `unknown` (L:267-274) [O]. `decide_manager_call` refuses while anything is unresolved (L:520-521) [O]. Nothing is resent. The attempt is blocked, which is chunk 2 work.
- **Replay of completed manager calls (U1).** The call id digests the prompt (X:478-483, RN:181-199) [O]. If MAF regenerates identical prompts, the replay returns the stored output with no send (L:509-516, G:803-806) [O]. If a prompt differs, the call id differs, sequence 1 is already taken, and `ContractError` is raised (L:517-519) [O]. That is also safe, but it cannot make progress. **Whether MAF prompt serialization is byte-identical across a fresh start is [U].** `Message.to_dict()` (RN:181) may carry per-run identifiers, and no test covers a fresh-start replay. The existing restore test only answers from a checkpoint (`tests/test_maf_delivery_lead.py:214-231`) [O].
- **Duplicate grant (U4, U5).** The re-proposed action gets a new MAF checkpoint id, so its `action_id` differs (X:406-412, RN:310-317) [O]. `decide` finds the slot occupied with a different payload and raises (L:331-336) [O]. No second grant is issued. The attempt cannot continue either. The runner may also see two checkpoints pending `flow-magentic-action-1` (the stale file plus the new one) and abort as ambiguous (RN:306-309) [I].
- **Meaning change (U2).** On replay, `decide_manager_call` returns the stale allowed grant (L:514-516). `consume_manager_grant` then either finds it expired and rewrites the row to `denied/grant_expired` (L:566-569), or, within 60 seconds, consumes it as a first send [O]. The first outcome changes the row from "authorized, unsent" to "denied". That violates the third safety condition.
- **U0.** A replay is equivalent to a fresh start [I]. Whether MAF left superstep checkpoint files that make the pending-checkpoint lookup ambiguous is [U].

### 1.3 Verdict: `fail-closed` (`no_restorable_checkpoint`)

**Rule [R].** Chunk 1 recovery requires a bound worker checkpoint for the attempt's highest-sequence action row. Otherwise it refuses with `no_restorable_checkpoint`, before any claim or mutation. The same rule refuses U5, not only the "first action" case named in `solution.md`.

**Why a replay is not adopted [I].** No ledger change can make U4 or U5 progress, because the action identity is bound to a checkpoint id that no longer exists. U1 progress depends on an unverified MAF determinism property. U2 needs a new grant rotation just for this path. A replay is safe only inside a narrow envelope:

- S1: no action rows;
- S2: every manager-call row is `completed`;
- S3: no file in `checkpoint_dir` holds a pending `flow-magentic-action-*` request;
- S4: MAF prompt serialization is byte-deterministic [U];
- S5: the worktree still equals the charter baseline (G:354-366).

The operator already has an equivalent remedy: a lead resume or supersede followed by a fresh successor attempt (design items 8 and 9). The only cost is repeating the completed manager calls.

**Consequences for the tests.**

- The AC4(b) kill point must sit **between** the bind (G:904) and the grant consumption (G:906). For the verifier it sits between G:904 and `prepare_verifier_send` (G:922).
- A kill before the bind is a separate refusal test that expects `no_restorable_checkpoint` and asserts zero mutation.

**Revisit the rule when** a spike proves S4 on the pinned MAF version and U0/U1 recovery has operator demand. The replay would then be an additive `baseline_replay` mode, guarded by S1-S5.

---

## 2. File-level design for chunk 1

### Components (new and changed)

- **New `cli/delivery_recovery.py` [R].** A pure domain module with no I/O and no imports of G or C:
  - `recovery_eligibility(envelope, snapshot, *, lead_active: bool) -> dict`, which returns `recoverable`, `reason`, `mode`, `checkpoint`, `blockers[]`, and `predecessors[]`;
  - `rebuild_chartered_evidence_plan(envelope, snapshot) -> dict`, which decides whether test evidence is reused or captured, from which binding, and the expected `diff_digest`;
  - `build_recovery_block(snapshot, *, replaced_draft_sha256) -> dict`;
  - the stable reason-code constants.

  This separates domain rules from integration, as `architecture.md` requires ("Domain rules").
- **`cli/execution_ledger.py`:** new tables, claim/CAS, release, regrant, interruption, superseded seal, and `sealed_receipt_sha256`.
- **`cli/delivery_gateway.py`:** routing, `_resume_chartered`, the interruption branch, the seal seam, the runtime-outcome event, the receipt builder, and evidence reuse.
- **`cli/execution_contracts.py`:** `predecessors` envelope validation and the v8 receipt `recovery` validator.
- **`cli/delivery_control.py`:** the ledger-backed lead guard and the superseded seal.
- **`cli/delivery_projection.py`:** eligibility, blockers, predecessors, and the sealed-digest check.
- **`runtime/maf_runner/delivery_lead.py`:** the `pending` restore mode.
- **`cli/maf_supervisor.py`:** no change, because it passes `resume` through unchanged (S:467) [O].
- **ADR:** `docs/adr/0016-chartered-v8-recovery.md`.

### Item 1: Routing

- **`resume_delivery`** (G:567-655).
  - Right after the snapshot (G:581), open the ledger read-only and branch on the protocol version. The check at G:584 becomes the v5 branch only.
  - v8 goes to `_resume_chartered(work_id, attempt_id, root=..., manager_adapter=..., worker_adapter=..., supervisor=..., test_runner=..., python_path=..., actor="flow-chartered-resume", seal_hook=None)`.
  - v6 raises `RecoveryRefused("v6_inspection_only")`. v7 raises `RecoveryRefused("v7_not_recoverable")`. [R]
  - `continuation_epoch_id` is refused for v8 (`continuation_epochs_v5_only`), because ADR 0013 stays v5-only.
- **`recover_delivery`** (G:658-731).
  - Branch before the v5 check at G:675. v8 calls `_resume_chartered(..., actor=actor)`.
  - In chunk 1, v8 `recover` is the same as `resume`, because chunk 1 needs no operator evidence. Chunk 2 adds evidence import here.
  - v6 and v7 are refused as above. [R]
- **`RecoveryRefused(ContractError)`** is a new exception with `.reason`, and its `str()` starts with the reason code.
  - The CLI already catches `ContractError` and `ValueError` (F:981, F:990), so no CLI change is needed for refusals [O].
  - [R] Emit `{"status":"refused","reason":<code>,"detail":...}` in JSON mode.
- **Terminal attempts.** If the status is not `started`:
  - if `attempt_recoveries` has rows, return the current state (`{"status": <terminal>, "receipt_path": ..., "replayed": true}`) with no mutation, which satisfies AC2;
  - otherwise refuse with `attempt_terminal`, which satisfies AC1.
- **No mutation before the gate [R].** Everything above uses `ExecutionLedger(path, read_only=True)` (L:37-43). The attempt directory and files are only read.

### Item 2: Interruption

- **`_execute_prepared_delivery` after the runtime outcome** (G:979-1006).
  - Today, chartered attempts are excluded from the interruption branch (G:986). A v8 transport loss is sealed `failed` and a v8 uncertain attempt is sealed `unknown` (G:1005) [O].
  - [R] Add a v8 branch before G:993:

    ```
    if structured_verifier and (uncertain or (failure and recoverable_transport_failure)):
        cause = "reconciliation_required" if uncertain else "transport"
        with authority_guard(), ledger.send_lock():
            ledger.record_interruption(aid, cause, failure[:512], generation=generation)
        return {"attempt_id": aid, "status": "interrupted", "reason": cause,
                "receipt_path": None, "resume_available": not uncertain, "blocking": [...]}
    ```

  - v5 keeps its `interruption.json` branch (G:986-992) unchanged. v6 and v7 still go through G:1005.
- **New `ExecutionLedger.record_interruption(attempt_id, cause, detail, *, generation)` [R].**
  - Requires `status='started'` and protocol 8.
  - Inserts an `attempt_interruptions` row and an `attempt_interrupted` event.
  - Append-only, and idempotent on `(attempt_id, owner_generation, cause)`.
- **`finish_attempt`** (L:1235-1250) [R]:
  - For protocol 8, refuse `status == "unknown"` with `"protocol v8 never seals an unknown receipt"`. This is defense in depth behind the gateway branch.
  - v5-v7 keep the parity rule at L:1244-1248.

### Item 3: Exclusive claim

- **Where the exclusive claim lives.** It has two parts.
  1. **Process-level (fast fail).** A non-blocking `fcntl.flock(LOCK_EX | LOCK_NB)` on `execution/recovery-<attempt_id>.lock`.
     - Put the lock beside the ledger, not inside the attempt directory. P:102 picks the default attempt by the attempt directory's mtime, and a lock file inside it would change that choice [O].
     - Hold it for the whole recovery, including the MAF restore.
     - `BlockingIOError` raises `recovery_in_progress`.
     - New helper: `ExecutionLedger.recovery_lock(attempt_id)`, a context manager modelled on `send_lock` (L:194-205).
  2. **Durable (survives process death).** `ExecutionLedger.claim_chartered_recovery(attempt_id, *, expected_generation, lead_generation, actor, checkpoint, quarantined) -> dict`. It runs inside `send_lock` and `BEGIN IMMEDIATE`:
     - CAS: `owner_generation == expected_generation`, else `recovery_in_progress`;
     - protocol 8 and `status='started'`, else refuse;
     - `generation = expected + 1`;
     - turn `started` actions and manager calls into `unknown` (the same effect as L:267-274);
     - release unconsumed grants (item 6);
     - insert an `unmarked_process_exit` interruption if none was recorded since the last claim;
     - insert an `attempt_recoveries` row;
     - write a `recovery_claimed` event whose detail includes `recovery_id`.

     Factor the shared body out of `_claim_recovery_locked` (L:250-276) so that v5 `claim_recovery` behavior is byte-identical.
- **Lock order [R]:** `recovery_lock(attempt)` (non-blocking, outermost), then `run_lock` (inside `delivery_authority_guard`, C:40-55), then `send_lock` (L:194-205), then SQLite `BEGIN IMMEDIATE`.
  - This matches the existing `run_lock` then `send_lock` nesting at G:811, G:913, and G:1051 [O].
  - `run_lock` and `send_lock` are **not re-entrant**, because each call opens a new file descriptor and takes `LOCK_EX` (C:30-32, L:198-201) [O]. `_resume_chartered` must therefore release both before it calls `_execute_prepared_delivery`, whose callbacks take them again per call [I].
- **Eligibility is checked before the claim [R].** Run `recovery_eligibility` on the read-only snapshot first. A blocked attempt (item 4) is refused **with no claim and no generation bump**. Re-running the command against a blocked attempt therefore never mutates anything.

### Item 4: Reconcile first, and checkpoint selection

- **Pure selection** in `recovery_eligibility` [R]:
  - Take the highest-sequence action row, `A`. Look up its `magentic_checkpoints` link, pending kind `worker` (L:1568, L:1584).
  - No link: `no_restorable_checkpoint` (§1).
  - Any action or manager call in `started` or `unknown`: `reconciliation_required`. Blockers list each id, its kind, its status, and "operator resolution (chunk 2)".
  - `A.status == completed`: `mode = "answer"`. This is the existing restore path (RN:263-297).
  - `A.status == allowed` with no `worker_dispatched` or `adapter_send_started` event (the same test as L:686-690 and L:936): `mode = "pending"`, which is boundary (b).
  - Any other `A` status: `checkpoint_position_unrecoverable`.
  - A `runtime_outcome_recorded` event exists: `mode = "seal"` (boundary i), and MAF is skipped.
- **Order in `_resume_chartered` [R]:**
  1. gate;
  2. eligibility;
  3. `recovery_lock`;
  4. under the authority guard and `send_lock`, `claim_chartered_recovery`;
  5. `read_magentic_checkpoint` (L:1141-1170) to re-verify the file digest;
  6. quarantine;
  7. evidence rebuild;
  8. restore.

  The ledger is reconciled in step 4, before the checkpoint is read or any grant is issued. That satisfies ADR 0012 and AC3.
- **Quarantine [R].** Every file in `checkpoint_dir` not referenced by `magentic_checkpoint_links` is moved to `checkpoints-quarantine/<recovery_id>/`, and its sha256 is recorded in `attempt_recoveries.quarantined_json`.
  - `_checkpoint_file` requires the bound file to sit directly under `checkpoint_dir` (L:984) [O]. Moving unbound files to a subdirectory therefore cannot affect bound reads.
- **New `pending` restore mode in RN [R].** `resume.kind = "pending"`, with `checkpoint_id`, `request_id`, `action_id`, `manager_calls_committed`, and `replans_committed`, and no `result`.
  - The runner loads the checkpoint (RN:270). It validates `reset_count` and the single pending request (RN:273-281).
  - It recomputes the identity with the resume `checkpoint_id` (RN:282-288) and checks it equals `action_id`.
  - It sets `action_number = saved["sequence"]`, `previous_action_id = saved["parent_action_id"]`, `manager_round = saved["manager_turn"]`, and `manager_call = manager_calls_committed`.
  - It **emits** the saved proposal (with `checkpoint_id` and `action_id`) exactly as RN:318 does, then continues the normal loop body (RN:319-324).
  - Answer mode keeps RN:263-297. The supervisor passes `resume` through (S:467), and its `schema_version==2` check applies only to other runners (S:171) [O].
  - Gateway resume dict: answer mode mirrors G:641-645. Pending mode omits `result`.
  - The manager-calls-committed and replan counts reuse the G:622-640 logic, factored out as `_restore_counters(snapshot, ledger_seq, envelope)`.

### Item 5: Evidence reuse and drift

- **Replace the G:778-788 preamble for v8 [R].** `_execute_prepared_delivery` gains a keyword-only `recovery: dict | None`. When it is set, it supplies `edit_evidence`, `test_evidence`, and `verifier_input_sha256`, and the preamble does not run `test_runner`.
- **Rebuild in `_resume_chartered`, before the restore [R]:**
  - Deterministic diff check: `edit = _verify_chartered_edit(worktree, baseline, attempt_dir, job)` (G:525-550). Map its "recorded chartered diff changed" (G:545) and "editor changed the pinned source commit" (G:528) errors to `RecoveryRefused("worktree_drift")`.
  - If verifier inputs exist (L:1563, L:1588), all of them must share one `diff_digest` and one `test_digest`; otherwise `evidence_binding_conflict`. Also require `edit["diff_sha256"] == inputs[-1]["diff_digest"]`; otherwise `worktree_drift`.
  - Then set `tests = {"command": envelope["job_contract"]["test"]["argv"], "status": "passed", "output_sha256": <final evaluation's input test_digest, else latest input's>}`.
  - The shape matches G:564 exactly [O], and the command is pinned in the envelope (G:386) [O].
  - Reuse is sound because `prepare_verifier_send` runs only after G:948 produced passing evidence (G:855-856, G:924) [O].
  - If no verifier input exists (boundary d), run `test_runner` exactly once, then re-verify that the edit is unchanged, as G:949 does.
  - All of this happens after the claim and before the restore. A drift refusal therefore makes no provider send and completes nothing (AC7). The claim row and interruption remain as the record of the failed attempt [I].
- **Stale-evidence gate** (G:999-1004). It is unchanged. With reused evidence it passes by construction, because `test_evidence["output_sha256"]` equals the binding's `test_digest`, which equals `evaluation.test_evidence_digest` (L:790-792) [I].
- **Residual risk [I].** At boundary (d), `repair.diff` may not exist yet (a crash between G:942 and G:947), so there is no durable reference to check drift against. The worktree is re-verified for scope and baseline and becomes the recorded diff. This is acceptable because the verifier has not judged anything yet. ADR 0016 should record it.

### Item 6: Boundaries

- **(b) Release [R].** Inside `claim_chartered_recovery`, every action with `status='allowed'` and no dispatch events becomes `not_dispatched`, with `reason='recovery_unconsumed_grant'` and `grant_id=NULL`, plus a `recovery_grant_released` event.
  - The released ids go into `attempt_recoveries.released_json`.
  - `paid_count` already counts `not_dispatched` (L:367), so the row counts once whether it is released or not [O].
- **(b) Regrant [R].** New `ExecutionLedger.regrant_recovered_action(envelope, action, *, generation) -> decision`, in one transaction:
  - the row is `not_dispatched`, its reason is `recovery_unconsumed_grant`, and `request_json == canonical(action)`;
  - no dispatch events exist;
  - `_assert_owner` passes;
  - the v8 `decide` limits hold, computed **excluding this row**: paid (L:364-369), delegations (L:376-380), concurrency (L:381-385), and the verifier cap and retry rules (L:386-410);
  - then set `status='allowed'`, `reason='recovery_regranted'`, and a new `grant_id`, and write a `policy_allowed` event with detail `recovery_regranted` (finding 5).

  Gateway hook: in `on_action`, after `decide` returns `replayed` with `not allowed` and `reason == "recovery_unconsumed_grant"` (it takes the G:888 branch today), call the regrant under `authority_guard`, then fall through to G:892. `decide` itself is unchanged, so v5-v7 are unaffected.
- **Manager tail [R].** New `ExecutionLedger.reissue_recovered_manager_grant(call_id, *, generation)`. It requires `allowed`, no `manager_send_started` event, and an active recovery for this generation. It rotates `grant_id`, keeps the status `allowed`, and writes a `manager_policy_allowed` event with detail `recovery_regranted`.
  - Gateway hook: at G:803-813, when the decision is replayed and allowed during a recovery.
  - The manager status set in the receipt is unchanged (X:758) [O].
- **(f)** Answer mode needs a rebuilt reply when `action-<id>.result.json` is absent. `_rebuild_reply(snapshot, action, evidence)`:
  - for a verifier: ensure an evaluation through `record_verifier_evaluation` (idempotent, L:794-798), then `verifier_summary` (G:841-846);
  - for a producer: the G:960-962 summary with the reused evidence.

  This is the same logic as the replay branch at G:859-887, factored into a helper both call sites use.
- **(g) and (h)** use answer mode with the verifier's result. A retry is gated by L:405-410, and the retry input reuses the same `test_digest` [O].
- **(i)** Mode `seal` skips MAF and calls the extracted receipt builder (item 7) using the recorded outcome.
- **New event `runtime_outcome_recorded` [R].** Written through a new `ExecutionLedger.record_runtime_outcome(attempt_id, outcome, *, generation)` right after G:981, **only** when the gateway commits to sealing (not interrupted).
  - Detail: `canonical({"failure": failure[:512], "transport": bool, "outcome_attempt_id": ...})`.
  - It is idempotent per generation.

### Item 7: Receipt, `recovery` block, validator, sealed digest

- **Extract the receipt builder [R].** Move G:1005-1047 into `_build_chartered_receipt(envelope, attempt_dir, ledger, *, failure, edit_evidence, test_evidence, verifier_input_sha256, continuation_epoch_id)`. This is a pure refactor in its own commit, and the normal and `seal`-mode paths both use it.
- **v8 `recovery` block** (a top-level receipt key, v8 only, present iff `attempt_recoveries` has rows):

  ```
  "recovery": {
    "schema_version": 1,
    "interruptions": [{"interruption_id", "cause", "owner_generation", "recorded_at"}],
    "recoveries": [{"recovery_id", "expected_generation", "generation", "lead_generation",
                    "actor", "released_action_ids": [...], "claimed_at"}],
    "resolutions": ["<resolution_id>", ...],   // chunk 1: from snapshot["resolutions"]; normally []
    "replaced_draft_sha256": "<hex>" | null
  }
  ```

  - **Draft [R].** If `receipt.json` exists while the ledger status is `started`, it is an unsealed draft (a crash between G:1058 and G:1059). Record its sha256, then overwrite it atomically.
- **Validator** in `_validate_magentic_receipt`, under `has_structured_verifier_evaluations` (X:777) [R]:
  - (a) Shape and enums. The cause is one of `transport`, `reconciliation_required`, `unmarked_process_exit`.
  - (b) `recoveries[0].expected_generation == delivery_lead_claim.generation`. Each later `expected_generation` equals the previous `generation`, and generations strictly increase. Every `lead_generation` equals the envelope claim.
  - (c) Every `owner_generation` in `checkpoints`, `verifier_inputs`, and `verifier_evaluations` lies in `{claim.generation} ∪ {r.generation}`. **This catches a changed generation.**
  - (d) The block is **required** when any action reason is in `{recovery_unconsumed_grant, recovery_regranted, recovery_after_dispatch}` or starts with `operator_resolved_`, or when any `owner_generation` in (c) exceeds the claim generation. **This catches a removed marker** in boundaries b, d, and g.
  - (e) The union of `released_action_ids` equals the set of actions whose reason is `recovery_unconsumed_grant` or `recovery_regranted`.
  - (f) `resolutions` equals the resolutions behind actions whose reason starts with `operator_resolved_`. Chunk 2 extends this to manager calls.

  Receipts without the key and without any trigger in (d) validate exactly as they do today. v5-v7 never reach this branch [O]: X:777 applies to protocol 8 only (X:49-51).
- **R2, the limit of receipt-only checks [I].** Removing the marker from a (h) or (i) recovery leaves nothing a receipt-only check can see. The ledger closes this gap, as the next bullet describes.
- **`sealed_receipt_sha256` [R].**
  - Add `ALTER TABLE attempts ADD COLUMN sealed_receipt_sha256 TEXT` using the `PRAGMA table_info` idiom (L:154-162).
  - For protocol 8, `finish_attempt` reads the receipt file and stores its sha256 in the same transaction, following the `finish_magentic_continuation` precedent (L:1257-1260, L:1274).
  - Expose the column in `snapshot` (L:1552-1555).
  - Inspection compares it with `sha256(receipt.json)` and reports whether `attempt_recoveries` exists but the receipt has no `recovery` block.

### Item 8: Lead change, the ADR 0014 amendment

- **`change_lead_claim`** (C:210-288).
  - Replace the inert check at C:239 (`pending_unknown_actions` is never written [O]) with a ledger read, for `resume` and `supersede` only.
  - The ledger is at `run_dir/"execution"/"ledger.sqlite"` and is opened with `read_only=True`. If it cannot be read, fail closed with `"delivery ledger unreadable; lead change refused"` (R6). If the ledger is absent, there is nothing to block.
  - If any `started` attempt of this `work_id` has actions or manager calls in `started` or `unknown`, refuse with the existing message `"unknown action blocks Delivery Lead successor"`.
  - `attention` and `release` stay unguarded, and lifecycle abandonment is untouched, so abandonment remains available.
- **Superseded seal, ordered before the claim bump [R].** Still inside `run_lock` (C:229), before `_write_immutable` at C:273, call the new `ExecutionLedger.seal_superseded_attempts(work_id, *, lead_generation, successor_generation, action)`. Under `send_lock` and `BEGIN IMMEDIATE`, for each `started` v7 or v8 attempt whose envelope claim generation equals `lead_generation`:
  - bump `owner_generation`, which fences any live process through `_assert_owner` (L:223-224);
  - release unconsumed grants as `not_dispatched/superseded_unconsumed_grant`;
  - set `status='superseded'`, `reason=canonical({action, lead_generation, successor_generation})`, and `receipt_path=NULL`;
  - write an `attempt_superseded` event.

  A new ledger method keeps `finish_attempt` unchanged for v5-v7.
  - Lock order: `run_lock`, then `send_lock`, then SQLite, the same as elsewhere.
  - Crash safety: if the process dies after the seal but before `run.json` is written, the attempt is terminal and the claim is unchanged. A retry of `change_lead_claim` is then a no-op seal plus the bump [I].
- **Import boundary [O].** C imports only `delivery_contracts` and `fsutil`. L imports neither G nor C (L:17-29). [R] Import `execution_ledger` lazily inside `change_lead_claim`, which creates no cycle.

### Item 9: Successor lineage

- **Envelope [R].** `prepare_chartered_delivery` (G:233-415) opens the ledger before minting (read-only when the file exists). It collects every attempt of `work_id` with protocol 8 and builds `predecessors = [{attempt_id, terminal_status, receipt_sha256 (sealed_receipt_sha256 or null for superseded), lead_generation}]`, sorted by creation. The list is added to the envelope at G:387-409 **only when non-empty**, so first attempts stay byte-identical.
- **Sibling gate [R].** If any predecessor is `started`, refuse with `sibling_attempt_not_terminal`. `create_attempt` (L:235-244) re-checks this inside `BEGIN IMMEDIATE`, which closes the race between two prepares.
- **`create_attempt` [R].** For protocol 8 with `predecessors`, the list must equal exactly the ledger's attempts for `work_id`, with matching status and sealed digest. Otherwise `predecessor_link_invalid`. Requiring set equality stops a successor from dropping a predecessor to evade the limits in item 10.
- **Validator [R].** A new `_validate_predecessors(envelope)` in X, called from `validate_envelope` (X:96-106) only when the protocol is 8. It checks the list shape, hex digests or null, that `terminal_status` is terminal, and that `lead_generation` is below `delivery_lead_claim.generation`. v7 envelopes are not re-validated, so their behavior is unchanged.
- **Tamper evidence [O].** The receipt binds `envelope_digest` (X:712), and the envelope contains `predecessors`.
- **Task facts [R].** Append one line per predecessor to the G:761-768 facts: "Predecessor attempt <id> ended <status> under lead generation <n>; its evidence is not reused." The facts derive from the envelope, so they are deterministic across restores.

### Item 10: Limits across a lineage

- **In the `decide` v8 branch** (L:353-418) [R], let `pred = [p["attempt_id"] for p in envelope.get("predecessors", [])]`.
  - `paid_count += count(actions of pred with paid provider AND status IN ('started','completed','failed','unknown'))`. This counts sends, not released grants.
  - `verifier_lineage = sum of _verifier_usage(pred).consumed` (L:805-820).
  - The cap rule at L:405 uses `verifier_reserved + verifier_lineage`. The **retry rule at L:407-410 stays per attempt.** Otherwise a successor's first verifier would be refused as `verifier_retry_denied`, because the lineage count is above zero and there is no evaluation in the attempt [I].
- **Consistency with the receipt [R].** `_verifier_usage.retry_eligible` (L:820) and the receipt recompute (X:846-857) must agree with `decide`. Add a v8-only receipt field `lineage_usage: {"predecessor_paid_calls", "predecessor_verifier_sends"}` when predecessors exist. Compute `retry_eligible` as `reserved + predecessor_verifier_sends < maximum` in both places.
- **Open decision for the engineer [U].** Manager model calls are paid for Claude and Codex managers (L:546), but `solution.md` only lists paid worker calls and verifier sends. A successor therefore gets a fresh `max_manager_calls`. Record this in ADR 0016, or extend the lineage count. Extending it risks making a successor unable to finish.

### Item 12: Inspection

- **`inspect_delivery_projection`** (P:21-53) [R]:
  - Add a keyword `lead_active: bool`, computed in `inspect_delivery` from `run.json` with the C:49-54 rule. Fix `executable` and `resumable` to use `status == "started" and lead_active` (finding 3).
  - Add `recovery = recovery_eligibility(envelope, snapshot, lead_active=...)`, which gives `recoverable`, `reason`, `mode`, and `blockers: [{id, kind: action|manager_call, status, reason, evidence_needed}]`.
  - Evidence needed:
    - an unknown action needs "resolve-execution: resolved_completed with a durable observed response, or resolved_not_dispatched with positive_no_send evidence (chunk 2)";
    - an unknown manager call needs "manager-call resolution (chunk 2)";
    - a missing checkpoint needs "none; abandon, or lead supersede and start a successor";
    - an inactive lead needs "none; attempt fenced".
  - Also add `interruptions`, `recoveries`, `predecessors`, and `sealed_receipt: {ledger_sha256, file_sha256, matches, recovery_block_present}`.
  - The function stays pure and never grants anything.
- **`inspect_delivery`** (P:56-154). The ledger is already opened read-only (P:141) [O]. Add the `run.json` lead check and the receipt-file digest read.
- **CLI text output** (F:1018-1027) [R]: add `recoverable:`, `blocking:`, and `predecessors:` lines. JSON output carries the full structure.

### Item 13: Test seam

- **`_execute_prepared_delivery(..., seal_hook: Callable[[str], None] | None = None)`**, keyword-only [R].
  - It is also accepted by `execute_chartered_delivery` (G:514-522) and `_resume_chartered`, and it is **not** wired into F.
  - Call points:
    - `after-runtime-outcome`, right after the `record_runtime_outcome` commit;
    - `after-receipt-draft`, after `validate_receipt` (G:1048) and before the file is written;
    - `before-finish-attempt`, after `write_atomic` (G:1058) and before `finish_attempt` (G:1059).
  - It follows the `failure_point` style in C:171-204. Tests raise `KillPoint(BaseException)` (finding 6), then recover. They assert exactly one sealed receipt, zero sends, and a `replaced_draft_sha256` only for `before-finish-attempt`.

### New ledger DDL, all additive in the L:54-150 `executescript`

```sql
CREATE TABLE IF NOT EXISTS attempt_interruptions (
    interruption_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
    cause TEXT NOT NULL,              -- transport | reconciliation_required | unmarked_process_exit
    detail TEXT NOT NULL,             -- bounded 512 bytes
    owner_generation INTEGER NOT NULL,
    ledger_seq INTEGER NOT NULL,      -- events high-water at record time
    recorded_at TEXT NOT NULL,
    UNIQUE(attempt_id, owner_generation, cause)
);
CREATE TABLE IF NOT EXISTS attempt_recoveries (
    recovery_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
    expected_generation INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    lead_generation INTEGER NOT NULL,
    actor TEXT NOT NULL,
    mode TEXT NOT NULL,               -- answer | pending | seal
    checkpoint_json TEXT,             -- {pending_id, checkpoint_id, file_sha256} or NULL for seal
    interruption_ids_json TEXT NOT NULL,
    released_json TEXT NOT NULL,      -- action ids released as recovery_unconsumed_grant
    quarantined_json TEXT NOT NULL,   -- [{name, sha256}]
    claimed_at TEXT NOT NULL,
    UNIQUE(attempt_id, generation)
);
-- attempts: ALTER TABLE attempts ADD COLUMN sealed_receipt_sha256 TEXT   (PRAGMA-guarded, L:154-162 idiom)
```

- **Compatibility [I].**
  - Every change is additive, and every row is insert-only; no update statements exist for the new tables.
  - Old databases gain empty tables. `snapshot` must guard the new selects with the `tables` presence set (L:1561) and the column set (L:1552).
  - No v5-v7 path writes the new tables or column.
  - `status='superseded'` needs no DDL because `attempts.status` is free text (L:57) [O].
- **Rollback [I].** Code reverted to `9436527` ignores the new tables and column.
  - A `superseded` attempt then reads as a non-`started` status, and `decide` refuses it (L:319-321), which is safe.
  - A v8 attempt left `started` with an interruption row becomes the pre-change "stuck `started`" state, which is also safe.
- **Chunk 2 note [R].** The `solution-data.md` unique index on `recovery_resolutions(attempt_id, action_id)` is deferred to chunk 2, which owns resolutions.

### Stable reason codes (new)

`v6_inspection_only`, `v7_not_recoverable`, `attempt_terminal`, `continuation_epochs_v5_only`, `lead_generation_inactive`, `recovery_in_progress`, `reconciliation_required`, `no_restorable_checkpoint`, `checkpoint_position_unrecoverable`, `worktree_drift`, `evidence_binding_conflict`, `envelope_changed`, `sibling_attempt_not_terminal`, `predecessor_link_invalid`.

---

## 3. Commit sequence for chunk 1

Each commit is one logical change and must pass `python3.12 -m unittest discover -s tests` on its own.

1. `docs(adr): add ADR 0016 chartered v8 recovery`. Covers the decision, the ADR 0014 amendment, the consequences, rejected alternatives B and C, the R1 verdict, and the manager-call lineage decision.
2. `feat(ledger): add v8 interruption and recovery tables and sealed receipt digest column`. Schema, snapshot exposure, and an old-database migration test. No behavior change.
3. `refactor(gateway): extract chartered receipt builder and reply rebuild helpers`. Pure refactor of G:1005-1047 and G:859-887. Existing tests unchanged.
4. `feat(gateway): record v8 interruptions instead of sealing transport loss or unknown`.
   - Adds `record_interruption`, the v8 branch at G:986-1006, and the `finish_attempt` v8 unknown refusal.
   - Inverts and renames the test at `tests/test_chartered_delivery_gateway.py:725` (finding 7).
5. `feat(gateway): add seal_hook test seam and runtime_outcome_recorded event`.
6. `feat(contracts): validate predecessors and the v8 receipt recovery block`. Validator only. Tamper subtests use hand-built receipts. A v7 completed-receipt regression test is included.
7. `feat(recovery): add pure recovery eligibility and evidence plan module`. Adds `cli/delivery_recovery.py` with table-driven unit tests over snapshots, including the R1 U0-U5 cases.
8. `feat(ledger): add exclusive chartered recovery claim, grant release, and regrant`. Adds `recovery_lock`, `claim_chartered_recovery` (CAS), `regrant_recovered_action`, `reissue_recovered_manager_grant`, and `record_runtime_outcome`.
9. `feat(runtime): add pending-request restore mode to the delivery lead runner`. Tests are gated on MAF availability, like `tests/test_maf_delivery_lead.py`.
10. `feat(gateway): route resume and recover by protocol with stable refusals`. v6, v7, terminal, and v8 gates. Temporarily, v8 returns `no_restorable_checkpoint` or refuses through eligibility only. Includes the AC1 no-mutation snapshot tests.
11. `feat(gateway): recover chartered v8 attempts from the latest bound checkpoint`.
    - Adds `_resume_chartered` (claim, quarantine, evidence rebuild, restore, continue, seal), the `recovery` block, and `replaced_draft_sha256`.
    - Includes the AC4 chunk 1 kill matrix, AC6, AC7, AC8, and the AC2 concurrency test.
12. `feat(delivery): seal superseded attempts and guard lead changes on ledger uncertainty`. Covers AC9.
13. `feat(delivery): link successor attempts to predecessors and count limits across the lineage`.
14. `feat(inspect): report v8 recovery eligibility, blockers, predecessors, and sealed digest`. Covers AC11 and fixes finding 3.
15. `test(recovery): add mutation-check harness for the AC6 test-runner guard`. The AC12 chunk 1 half. Document the procedure: disable the reuse branch and show the named assertion `test_runner_calls == 0` fails.

Ordering notes:

- Commits 6-9 add capabilities nothing calls yet, so each is green alone.
- Commit 4 lands before 11 so that no v8 attempt is ever sealed `unknown` in between.
- Commit 12 must follow 11, because the `superseded` status must exist in eligibility and inspection code paths.

---

## 4. Recovery sequence diagram

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator (CLI)
    participant G as Gateway _resume_chartered
    participant R as delivery_recovery (pure)
    participant RL as recovery_lock (flock NB)
    participant A as delivery_authority_guard (run_lock)
    participant L as ExecutionLedger (send_lock + SQLite)
    participant W as Worktree
    participant M as MAF runner (restore)
    participant P as Providers

    Note over G,P: Interrupt — live run hits transport loss / uncertain send / process death
    G->>L: record_interruption(cause) [v8, no finish_attempt, no receipt]
    Note over L: attempt stays `started`; no terminal `unknown` for v8

    Op->>G: flow run resume-delivery-lead (or recover-delivery-lead) work attempt
    G->>L: snapshot (read_only=True)
    G->>R: recovery_eligibility(envelope, snapshot, lead_active)
    alt v6 / v7 / terminal / blocked / no bound checkpoint
        R-->>G: refuse(reason)
        G-->>Op: refused (no mutation)
    end
    G->>RL: acquire LOCK_EX|LOCK_NB
    alt already held
        RL-->>G: BlockingIOError
        G-->>Op: recovery_in_progress
    end

    Note over G,L: Recovery claim + Reconcile (ledger first, ADR 0012)
    G->>A: enter (lead generation active?)
    A->>L: send_lock → BEGIN IMMEDIATE
    L->>L: CAS owner_generation == expected → +1
    L->>L: started→unknown; allowed(no dispatch)→not_dispatched(recovery_unconsumed_grant)
    L->>L: insert attempt_recoveries (+ unmarked_process_exit interruption if none)
    L-->>G: generation, recovery_id
    G->>A: exit (run_lock and send_lock released)

    Note over G,W: Evidence rebuild
    G->>L: read_magentic_checkpoint (digest re-verified)
    G->>G: quarantine unbound checkpoint files
    G->>W: _verify_chartered_edit (deterministic diff)
    alt diff ≠ recorded / binding diff_digest
        G-->>Op: worktree_drift (no send, nothing completed)
    end
    alt verifier input exists
        G->>G: tests = {job.test.argv, passed, final binding test_digest} (no test run)
    else before any verifier input
        G->>W: run targeted test exactly once
    end

    alt runtime_outcome_recorded present (boundary i)
        G->>G: skip MAF
    else Restore
        G->>M: resume {answer | pending} at latest bound checkpoint
        Note over G,P: Continue — every call re-enters Flow's ledger
        M->>G: replayed manager/action requests
        G->>L: decide → replayed rows return stored results (no send)
        G->>L: regrant_recovered_action / reissue manager grant (counted once)
        G->>P: only newly granted sends
        M-->>G: workflow_finished
        G->>L: record_runtime_outcome
    end

    Note over G,L: Seal
    G->>G: build receipt + recovery block (replaced_draft_sha256 if draft existed)
    G->>G: validate_receipt (v8 recovery cross-checks)
    G->>A: enter
    A->>L: send_lock → assert_owner → finish_attempt(+ sealed_receipt_sha256)
    G-->>Op: terminal status + receipt path
    G->>RL: release
```

---

## 5. Chunk 2 outline (components only), and R5

### Chunk 2 components

1. **Ledger: `manager_call_resolutions`.** An append-only table keyed by `(attempt_id, call_id)` and bound to `owner_generation`, plus a new `resolve_unknown_manager_call`. Today's `recovery_resolutions.action_id` references `actions` (L:100), so manager calls cannot be resolved [O]. The chunk also adds the `recovery_resolutions(attempt_id, action_id)` unique index, following the `solution-data.md` tolerant-migration pattern.
2. **Operator response import (boundary layer).** Normalizes operator-supplied response evidence for actions and manager calls, stored attempt-local as in EG:920-951. It is validated with the same checks as `observe_response` and `observe_manager_response` (L:829-859, L:574-596) before any resolution. The v5 precedent is G:698-719.
3. **v8 `resolve-execution` route.** An authority guard, the CAS claim from chunk 1, and v8-aware evidence kinds.
4. **Resolution-binding check at continuation.** Eligibility treats an `unknown` item as unblocked only when a resolution matches its id, the attempt, and a generation in the attempt's recovery chain (AC5).
5. **Receipt.** The `recovery.resolutions` list is extended to manager-call resolutions. The AC10 added- and removed-resolution subtests use rule (f).
6. **Tests.** Boundaries (a), (c), and (e), the AC8 no-dispatch regrant, and the AC12 worker-adapter mutation check.
7. **Candidate, [R].** An "observation-backed" reconcile for an action with a durable `response_observations` row whose completion was interrupted (a crash between G:937 and G:942). The ledger already holds the response, so it may be resolvable using Flow's own evidence. That needs an ADR 0012 reading on whether an operator must still record it.

### R5: does `resolve-execution` support v8 today?

**Only mechanically, and not in the required sense. [O]/[I]**

- The route is F:1029-1041, then `resolve_attempt` (EG:899-955), then `inspect_attempt` (EG:601-632).
- `inspect_attempt` has no version gate. It checks v8's snapshot files (EG:618-623), which v8 does write (G:377-379) [O]. `recovery_version == 2` holds for v8 (L:243) [O].
- It then calls `claim_recovery` (L:246-248) and `resolve_unknown` (L:889-948). `resolve_unknown` is protocol-agnostic and checks the v8 verifier shape (L:924-930) [O].

The gaps [I]:

1. No `delivery_authority_guard` and no `run_lock`, so a fenced lead could still record resolutions.
2. It bumps the generation without a CAS, which races the chunk 1 claim. The CAS would refuse the stale caller, so this fails safe.
3. It cannot resolve manager calls (L:100, L:899-901).
4. There is no operator response import, so `resolved_completed` is impossible when the response was lost (L:917-919).

[R] Chunk 2 adds a v8 route with gaps 1-4 closed. [R, optional in chunk 1] Refuse v8 in `resolve_attempt` until then. A v8-only guard does not change v5-v7. Otherwise, document that a resolution recorded now is honored by the chunk 1 validator's rule (f).

---

## 6. Risks and tradeoffs (delta from `solution.md`)

- **The runtime change in chunk 1 (finding 1).** It adds MAF-gated test surface. It is contained to one additive resume mode, and answer mode is unchanged.
- **Quarantining checkpoint files (finding 2).** Moving files is a filesystem change. It is reversible and recorded. The alternative, a runner-side exclude list, spreads Flow policy into the runtime.
- **R2 residual.** Receipt-only checks cannot detect removing the marker from an (h) or (i) recovery. The ledger `sealed_receipt_sha256` check and the "recoveries exist but no block" check in inspection are authoritative.
- **Generation noise.** A refused eligibility check never bumps the generation. A drift refusal after a claim leaves one claim row, which is intended as the audit record.
- **Lineage manager-call budget.** This is an open engineer decision (item 10).

## ADR recommendation

- Needed: **yes**.
- Title: **ADR 0016: Chartered v8 recovery**.
- Decision to capture:
  - Option A, and the R1 fail-closed rule with its revisit condition.
  - The pending restore mode and checkpoint quarantine.
  - That v8 never seals `unknown`.
  - Lock order: `recovery_lock`, then `run_lock`, then `send_lock`, then SQLite.
  - The ADR 0014 amendment: the superseded seal happens before the claim bump, the lead guard is ledger-backed, and abandonment remains available.
  - Predecessor set equality, and which limits are lineage-counted.
  - Consequences: ADR 0013 stays v5-only and v6 and v7 are unchanged.
  - Rejected alternatives B, C, and baseline replay.
