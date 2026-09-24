# Validation Results: chunk 1b

Validated on branch `codex/chartered-delivery-recovery-1b` at `e16e8bd`, against the change itself (no surrogate).

## Automated

- **Full suite:** `python3.12 -m unittest discover -s tests` → **1442 tests OK, 0 skipped** (`validation/full-suite.log`). The baseline on `main` `7b2b7ff` was 1426. The suite also passed after each code commit: 1432 at `c67d18f`, 1437 at `15e15b4`.
- **MAF-gated:** `tests.test_maf_delivery_lead` with the pinned interpreter (`FLOW_MAF_PYTHON=/private/tmp/flow-maf-runtime-spike-20260919/bin/python`) → **11 OK, 0 skipped** (`validation/maf-gated.log`). CI has no MAF job.
- **`git diff --check`:** clean.

## AC map

| AC | Proof |
|---|---|
| AC1 (AC9.2) superseded record | `test_lead_resume_seals_the_old_attempt_as_superseded`, `test_lead_supersede_seals_…`: status `superseded`, reason, released grant, `attempt_superseded` event, owner generation bumped, recovery refuses `attempt_terminal`, v7 row untouched |
| AC2 (AC9.3) lead guard | `test_lead_resume_or_supersede_is_refused_while_any_action_is_unknown` (full byte and snapshot comparison), `test_an_uncertain_v7_send_blocks_…` (started and unknown), `test_lead_change_fails_closed_on_an_unreadable_ledger`, `test_a_lost_or_symlinked_ledger_is_never_read_as_empty`, `test_lead_change_refuses_attempt_running_while_a_live_run_holds_the_lock`, `test_the_seal_refuses_attempts_that_were_not_probed` |
| AC3 (AC9.4) abandonment | `test_abandonment_succeeds_while_actions_are_unknown`: `release` and lifecycle `block` |
| AC4 lineage link | `test_successor_after_supersede_lists_the_superseded_predecessor`, `test_create_attempt_requires_the_exact_lineage` (dropped, added, altered status, digest, and generation), `test_first_attempt_has_no_predecessors_and_a_started_sibling_blocks_prepare`, `test_prepare_refuses_a_claim_that_changed_before_the_attempt_was_created`, validator `<=` case |
| AC5 lineage limits | `test_successor_paid_and_verifier_limits_count_predecessor_sends` (verifier cap and paid cap, denied before any adapter), `test_successor_first_verifier_is_not_a_retry` (plus task facts and receipt tamper), `test_tampering_only_lineage_usage_fails_receipt_validation` |
| AC6 suite and mutations | see above and below |

The AC9.1 test (from 1a) now models a stale generation by editing `run.json`, because a lead change seals the attempt.

## Mutation checks (`validation/mutations.log`)

Each check broke one behavior, confirmed the covering test fails, then restored the source (marker count 0 afterwards).

- **M1a**, read-only guard pre-check removed:
  - against the v8 unknown test: it **passed**, masked by the seal's in-transaction recheck;
  - against `test_an_uncertain_v7_send_blocks_…`, added for this reason: it **fails**.
- **M1b**, pre-check and in-transaction recheck both removed: the AC9.3 test **fails** (resume and supersede).
- **M2**, `decide` ignores the lineage: the lineage-limit test **fails** (`['editor', 'verifier'] != ['editor']`).
- **M3**, receipt lineage cap bound removed: the tamper test **fails** (the inflated verifier and paid subtests).
- **M4**, the seal ignores the probed set: `test_the_seal_refuses_attempts_that_were_not_probed` **fails**.

## Review

Quality and security implementation reviews ran read-only and concurrently: `research/implement-review.md` and `research/implement-review-security.md`. Between them: 0 blockers, 1 shared major (fixed), and minors fixed or dispositioned in the table in `implement-review.md`.

## Not run

- Live providers: none, by plan.
- A dedicated test for an `unknown` manager call as the guard trigger, and for the lineage count on the recovery regrant path (accepted residual).
