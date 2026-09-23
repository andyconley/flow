# Handoff: Chartered v8 Delivery Recovery, chunk 1a

- **Status:** chunk 1a is implemented, reviewed, and validated. It is ready for `flow-review` and a PR.
- **Branch:** `codex/chartered-delivery-recovery-1a`, local only and not pushed.
- **Worktree:** `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`.
- **Base:** the branch stacks on the definition and plan commits (`3fa6711` and `e43c109`) above `main` `6015e9b`. The engineer chose this stacking, so the 1a PR carries the definition and plan docs together with the code.

## What shipped

An interrupted protocol v8 chartered attempt is now recovered explicitly, on the same attempt, from its latest Flow-bound Magentic checkpoint (ADR 0016).

- **Interruption.** A v8 transport loss or uncertain send records an interruption, and the attempt stays `started`. v8 never seals `unknown`.
- **Entry.** `flow run resume-delivery-lead` and `flow run recover-delivery-lead` route v8 to `_resume_chartered`.
  - v6 refuses with `v6_inspection_only`, and v7 with `v7_not_recoverable`.
  - A terminal attempt refuses with `attempt_terminal`. If it has already been recovered, the command reports its current state instead.
  - `resolve-execution` refuses v8 with `v8_resolution_requires_chunk_2`.
- **Gates.** Eligibility is decided read-only. The possible refusals are `reconciliation_required`, `no_restorable_checkpoint`, `checkpoint_position_unrecoverable`, `lead_generation_inactive`, `worktree_drift`, `recovery_in_progress`, and `attempt_running`. The gates run again under the non-blocking `recovery_lock`. The live v8 run holds that same lock for its whole run.
- **Claim.** The claim is a compare-and-swap on the owner generation and the event high-water mark. It then:
  1. releases unconsumed grants;
  2. quarantines unbound checkpoint files;
  3. rebuilds evidence, reusing the bound test digest so the test is never rerun after a verifier input exists;
  4. restores MAF in `answer` or `pending` mode, or in `seal` mode skips MAF and seals.
- **Grants.** A released grant is re-granted once, under the limits and excluding itself. A never-sent manager grant is reissued in place.
- **Receipt.** The receipt carries a validated `recovery` block. The ledger stores the sealed receipt digest.
- **Inspection.** `inspect-delivery` reports whether the attempt is recoverable, its blockers and the evidence each needs, its interruptions, its recoveries, its predecessors, and the sealed-digest consistency.

Commits (Conventional Commits, and the full suite passed after each one):

- `27b68d5` ADR 0016
- `cdfb6bf` schema
- `85ae614` refactor
- `4a05beb` interruption
- `0c8d25c` seal seam
- `92756d0` contracts
- `7954471` pure module
- `72a8b3e` ledger claim
- `b69d1a1` runtime pending mode
- `4d3e5b6` routing and refusals
- `d164106` recovery
- `7de46ee` inspection
- `3a69f3f` review fixes

## Proof

- **Validation results:** see `validation-results.md`. The full suite ran 1420 tests with **0 skipped** (the baseline was 1370).
- **MAF-gated tests:** all 11 ran locally and none skipped (`validation/maf-gated.log`). This is the R9 merge gate, and the PR description must carry this log.
- **AC12 mutation check:** disabling evidence reuse fails the AC6 test. The source was restored, and the check was repeated on the final code.
- **Review:** see `research/implement-review.md`. The quality and security reviewers found 0 blockers and 3 majors, and all 3 are fixed. There were 18 findings in all, each dispositioned.

## Deviations from the plan

- `record_runtime_outcome` landed in commit 5 alongside the seal seam, instead of commit 8, because the seam needs it.
- Recovery tests live in the new `tests/test_chartered_delivery_recovery.py`, over a shared `CharteredFixture`. They are not in the gateway test class, which would have re-run 38 inherited tests.
- Commit 7 was amended once, because a guard test requires every `cli/` module to be registered and reachable. It was fixed before any later work.
- **Review-driven:** drift is checked before the claim, and the claim refuses `started` or `unknown` rows instead of fencing them.

## Residual risks

- **R2:** a receipt-only check cannot see a removed recovery block after a seal-mode recovery. The ledger's sealed digest and inspection are authoritative.
- **R8:** at boundary (d), when there is no `repair.diff` yet, the current worktree becomes the recorded diff, bounded by the baseline and scope checks.
- **Trailing denial:** a crash after Flow denies the latest proposal, and before the runtime outcome, refuses with `no_restorable_checkpoint` under R1. The remedy is supersede and a successor (1b).
- **Not covered in CI:** CI has no MAF job, so the pending-mode runtime test only runs locally.
- **Declined nits, recorded as follow-ups:** the raw-path read-only URI and `send_lock`'s missing `O_NOFOLLOW` both predate this diff.

## Next actions

1. `/flow-review chartered-delivery-recovery` to accept 1a.
2. On request: push the branch and open the 1a PR, with the MAF log in the body.
3. Chunk 1b (commits 12 and 13: the superseded seal, the ledger-backed lead guard, predecessors, and lineage limits) comes after 1a merges. Chunk 2 is a second cycle of this run.
4. The separate D4 scout (the v7 `close_pre_send_failure` allow-list) is still open.
