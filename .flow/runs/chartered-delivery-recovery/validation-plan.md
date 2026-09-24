# Validation Plan: Chartered v8 Delivery Recovery

The detailed test designs are in `research/plan-validation.md`: 29 named tests, with their fixtures and exact assertions. The corrections in `plan.md` "Validation" take precedence over that note.

## Acceptance criterion to proof (chunk 1)

- **AC1 (1a, commit 10).**
  - Tests: the v6, v7, and terminal-v8 refusals, and `resolve-execution` refusing v8.
  - Each refusal is checked with `_assert_ledger_unchanged` and a receipt byte comparison.
  - The v5 resume and recover suites stay green.
- **AC2 (1a, commit 11).**
  - Two concurrent recoveries yield exactly one, and the other gets `recovery_in_progress`.
  - A live attempt yields `attempt_running`.
  - Re-invoking after completion returns the current state with no mutation.
  - No time-, expiry-, or exit-triggered path exists.
- **AC3 (1a, commit 11).** The adapter doubles record the ledger's event high-water when each is called.
  - `recovery_claimed`, and then the call's grant event, both precede every adapter call.
  - Call counts are zero before the grant.
- **AC4, chunk 1 (1a, commit 11).**
  - Each boundary is killed with `KillPoint(BaseException)`, then recovered explicitly:
    - (b), between the checkpoint bind and the grant use;
    - (d);
    - (f);
    - (g);
    - (h);
    - (i), at `after-receipt-draft` and at `before-finish-attempt`;
    - clean transport loss.
  - Each test asserts the terminal status, the exact ordered sends, and the receipt `recovery` block.
  - (b) exercises the `pending` runtime mode, which is MAF-gated.
- **AC6 (1a, commit 11).**
  - Kill after `valid_pass`, using an injected test runner that returns a new digest on every call.
  - The attempt ends `completed`, the runner is called 0 times, and the final evaluation is bound to the reused `test_digest`.
  - At boundary (d), the runner is called exactly once.
- **AC7 (1a, commit 11).** The worktree is changed after the kill. Recovery fails with `worktree_drift`, makes zero sends, and completes nothing.
- **AC8 (1a, commit 11).**
  - A released and re-granted (b) action counts once against the paid, delegation, and verifier limits.
  - A verifier retry is granted only after `valid_fail` or `unusable` while allowance remains. Otherwise it is denied before any adapter is called.
- **AC9 (1b; the first clause is in 1a).**
  - (1) Refused once the lead generation is inactive (1a, commit 10).
  - (2) A terminal `superseded` record (1b, commit 12).
  - (3) A lead change is refused while an action is `unknown` (1b, commit 12).
  - (4) Abandonment still succeeds (1b, commit 12).
- **AC10, generation and marker (1a, commit 6).**
  - A separate subtest for each of: a changed generation and a removed recovery marker.
  - A completed v7 receipt still validates.
- **AC11 (1a, commit 14).**
  - `inspect-delivery` on a v8 attempt reports whether it is recoverable, each blocker with its reason, and the evidence each one needs.
  - A recovered attempt shows as executable.
  - The sealed digest is compared against the receipt.
- **AC12, test runner (1a).** A manual mutation check:
  - disable the evidence-reuse branch;
  - confirm the AC6 `test_runner` zero-calls assertion fails;
  - restore the branch, and confirm the suite is green again;
  - record the result in `validation-results.md`.

## Additional proof (from the plan design)

- **R1:** refuses with `no_restorable_checkpoint`, with zero mutation, for U4 and U5.
- **Quarantine:** a stale unbound checkpoint file does not produce a sealed `failed`, and its digest is recorded.
- **Manager grant re-issue:** a crash between the manager grant and its send recovers.
- **Old-ledger migration:** opening a pre-change ledger adds empty tables, and v5–v7 snapshots are unchanged.
- **1b, lineage:**
  - `test_successor_paid_and_verifier_limits_count_predecessor_sends`
  - `test_successor_first_verifier_is_not_a_retry`
  - predecessor set-equality refusal
  - the sibling-not-terminal refusal

## Chunk 2 (outline; traced at file level when it is re-planned)

- AC4 (a), (c), (e); AC5; the AC8 no-dispatch re-grant; the AC10 added- and removed-resolution subtests; and the AC12 worker-adapter zero-calls mutation.

## Commands, in order

1. The focused suites:
   ```
   python3.12 -m unittest tests.test_chartered_delivery_gateway tests.test_delivery_recovery tests.test_structured_verifier_ledger tests.test_maf_delivery_lead
   ```
2. The regression suites:
   ```
   python3.12 -m unittest tests.test_maf_recovery tests.test_execution_recovery tests.test_maf_continuation_supervisor tests.test_maf_post_resolution_continuation tests.test_delivery_projection tests.test_delivery_control
   ```
3. The full suite: `python3.12 -m unittest discover -s tests`. The baseline is 1370 tests passing with 0 skipped. **Zero skips is required** (R9).
4. `git diff --check`.
5. The AC12 mutation check, as described above.

## Merge gates (1a)

- Every command above is green, and the full suite reports 0 skipped.
- The PR description carries the local MAF-gated test log.
- The mutation result is recorded.
- No live-provider run is required, and none is made without the engineer's approval.
