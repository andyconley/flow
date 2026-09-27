# Review: producer-turn-contract

## Verdict

Ready to accept.

## Basis

- **Intent read:** `requirements.md`, `acceptance-criteria.md` (AC1–AC7), `plan.md`.
- **Change read:** `git diff fd4954b..46dbe23` across `cli/delivery_gateway.py`, `docs/maf-adoption-design.md` and `tests/test_chartered_delivery_gateway.py`.
- **Independent roles** (not the producer):
  - quality-reviewer (opus): Ready to accept.
  - test-engineer (sonnet): proof sufficient. Expertise lookup returned `no_match` (request `d4ca506a-0335-480d-ac0e-b40524c48afb`).

## Findings

- **Critical:** none.
- **Important:** none open.
  - The test-engineer found that the AC6 suite result was one commit stale (it ran at `fdb112b`, and `46dbe23` is test-only). **Fixed:** the full suite was rerun at `46dbe23`, with 1,571 OK and 0 skipped.
- **Suggestions**, accepted without change:
  - **S1:** a recovery `WORKTREE_DRIFT` refusal now carries "editor made no edit…" text when a recorded edit was lost. The old text ("outside scope") was also inaccurate there, and the drift code carries the context.
  - **S2:** check the byte cap with a `declared_regression` baseline kind. The block is about 800 bytes against a 1,500-byte cap.
  - **S3:** add an optional test for a mode-only change reaching branch (c).

## Factual check of the new facts line

- **"One call in total; Flow refuses any second editor call":**
  - v8: `_v8_action_checks` (`cli/execution_ledger.py:487-507`) refuses any producer instance once any producer has completed, and it is a hard refusal.
  - v6/v7: `:1128-1161` does the same.
  - A producer send that fails or has an uncertain outcome ends the attempt (`delivery_gateway.py` ~1598-1601).
- **"Flow checks the worktree right after it":** true. Verification runs directly after `ledger.complete` (~1587-1592).
- **"No edit fails the attempt":** true, and proven by the AC4 test.

## Requirement fit

All of AC1–AC7 are met.

- AC2 is a separate test method rather than a subtest, which is acceptable.
- No scope drift: `_verify_chartered_edit` admits and refuses exactly what it did before, and only the messages changed. There are no ledger, charter or schema changes. This matches decision 2a, guidance only.

## Validation fit

- Direct unit tests are real checks, and each would fail if its behaviour regressed.
- Mutations M1–M4 are recorded and can be replayed.
- The AC7 ledger scan is recorded.
- No live run was made; that is by design.

## Residual risks

- The manager may still ignore the guidance. The fail-closed check remains, and now reports the outcome accurately. `v8-live-validation-3` measures this.
- The archived `v8-live-validation` protocol-8 attempt can't be resumed after the `prompt_digest` change. This is accepted.
