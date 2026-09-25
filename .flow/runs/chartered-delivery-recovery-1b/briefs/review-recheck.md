# Brief: review recheck, chunk 1b

Run `chartered-delivery-recovery-1b`, lane `review`. Read-only; return findings inline.

## Task

The acceptance review (`review.md`) returned "needs refinement" with I1–I3 and S1, S2, S6. The orchestrator fixed them in the working tree (uncommitted, above `2760098`). You are the independent verifier: confirm each fix closes its finding, and that the fix introduces no regression.

- **Diff:** `git diff` in `/Users/andyconley/.codex/worktrees/delivery-recovery/flow` (working tree against HEAD): `cli/execution_ledger.py` (`_assert_receipt_lineage`, `finish_attempt`), `tests/test_chartered_delivery_recovery.py`, `docs/adr/0016-chartered-v8-recovery.md`, and the run evidence files.
- **Dispositions to check:** the "Refinement round" table at the end of `review.md`.
- **Specific questions:**
  1. I1: can the new seal check refuse an honest receipt? Consider a first attempt (no predecessors), a recovered attempt sealed in `seal` mode, a successor whose predecessor is `superseded` with a null digest, and a v5–v7 attempt (the check must be v8 only). Does the check run inside the same transaction as the status update?
  2. I2, S2: does each tightened assertion now test what the AC text says?
  3. S1: is the argument sound that an honest regrant cannot make the lineage count decisive, and is the direct `_v8_limit_reason` check an adequate pin?
  4. Evidence: do `validation-results.md` and `validation/mutations.log` match the test names at the working tree?

## Evidence inventory

- `review.md`, `validation-results.md` (the refinement section), `validation/full-suite.log` (1443 OK, 0 skipped), `validation/maf-gated.log` (11 OK), `validation/mutations.log` (M1a re-run, M5, M6 at the end).

## Output

A verdict (ready to accept, or needs refinement), and findings ranked critical, important, or suggestion, each with `file:line` and a claim status (observed, inferred, or unverified).
