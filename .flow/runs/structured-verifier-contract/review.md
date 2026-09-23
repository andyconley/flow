# Review: structured-verifier-contract

Reviewed 2026-09-23 against `requirements.md`, `acceptance-criteria.md`, `solution.md`, `validation-plan.md`, and `validation-results.md`, over `origin/main...codex/structured-verifier-contract` (8 commits) plus one review-lane fix.

Roles: coordinator review (code read and probed directly), `quality-reviewer`, and `test-engineer`. Neither delegated reviewer had shell access. The coordinator ran all tests. The test-engineer expertise query returned `no_match`, so no advisory entries were attached.

## Review Summary

### Verdict

- **Needs refinement.** The ledger authority is sound. Cap enforcement, retry eligibility, atomic grant and send claim, input binding, additive migration, and v7 compatibility all hold. The real-provider integration does not yet deliver AC1, and two AC4 paths are incomplete. Do not run `accept-review` until the Critical and Important items are resolved.

### Findings

**Critical**

1. **The verifier is never told the output contract.** Observed at `cli/delivery_gateway.py:853-860`. `provider_task` is the Magentic task plus the diff and test evidence, and the verifier instructions come from the general role persona (`_effective_specialist_for`). Outside the evaluator and validators, nothing in `cli/`, `runtime/`, or the scaffolds mentions `schema_version`, `decision`, `findings`, or `non_blocking`. The inferred failure: a real Ollama verifier answers in prose, every call is `unusable`, the one retry is too, and no chartered job can complete. AC1 is proven only with stub output. AC10 assumed that a contract-eliciting prompt exists. **Fix:** add a fixed, versioned contract instruction to `provider_task`, inside the persisted and digested verifier input, and test that the input carries it.

**Important**

2. **FIXED in review.** A non-string `decision` or `severity` raised `TypeError` at `cli/verifier_contracts.py:83,93`. I reproduced `{"decision":[]}` and `{"severity":{}}`. The error came after `ledger.complete()`, so no evaluation was recorded, the attempt failed with a raw Python error message, and the retry was lost. The fix adds `isinstance(..., str)` guards. Two regression cases were added to `tests/test_verifier_contracts.py`, and both inputs now return `unusable` with `candidate_decision_invalid` or `candidate_finding_severity_invalid`. The fix was committed in `8a18415`.
3. **A completed verifier call is not re-evaluated on resume.** Observed at `cli/delivery_gateway.py:834-847`. The replay branch returns the raw provider output and never calls `evaluate_candidate`, which is only called at `:908`. A crash between `complete()` and `record_verifier_evaluation()` leaves a completed verifier call with no evaluation. Magentic then gets prose, and `decide()` denies the retry because the latest outcome is `None`. This is the missing mitigation for an owned risk in `solution.md`. **Fix:** in the replay branch, re-evaluate from the stored response and `verifier_inputs`, then record the result idempotently.
4. **Ollama adapter faults on v8 verifier calls become `unknown`, not `unusable`.** Observed at `cli/local_worker.py:77-80`. Empty content and a mismatched model raise before any result exists, so gateway `:922-924` marks the call `unknown`. That contradicts requirement 6 and AC4: a received response should be completed, and a model mismatch should be `provider_binding_mismatch`. The adapter also truncates output to 4096 bytes (`_bounded_output`, `:19-20`). So `raw_output_digest` binds truncated text, and the evaluator's 16 KiB oversized path never fires for Ollama. **Fix:** on v8 verifier calls, return a normalized completed result that carries the mismatch facts, and make truncation explicit or flag it as unusable.
5. **Receipt validation does not recompute or cross-bind the evaluation.** Observed at `cli/execution_contracts.py:798-837`. It checks self-consistent digests. It does not re-run `evaluate_candidate` over the bound output and inputs. It does not compare the final evaluation's `diff_digest` and `test_evidence_digest` with `evidence.edit.diff_sha256` and `evidence.tests.output_sha256`. It does not require an evaluation for every completed verifier action. Every digest is unkeyed SHA-256, so an edit from fail to pass that is re-sealed consistently would validate. The one-producer rule stops the diff changing after verification, so this is a gap in proof, not a live bypass. **Fix:** recompute the evaluation and require equality, cross-check it against the evidence, and require one evaluation per completed verifier action.

**Suggestions**

- `schema_version: true` and `1.0` are accepted as version 1 at `verifier_contracts.py:81`, because `True == 1` in Python. Use `type(...) is int`.
- `validate_evaluation` accepts `valid_pass` paired with `accepted_fail`. Only the digest check catches it, and only incidentally. Tie each reason to its disposition.
- `delivery_gateway.py:405`: `canonical_limits.get("max_verifier_calls", 2)` projects a v8 cap from a charter that may never have sealed one. Require Charter v2, or record that the default was applied.
- A failure inside `prepare_verifier_send` (`delivery_gateway.py:880`) is outside the pre-send failure close at `:861-876`. The `grant_expired` update can roll back, and the action then stays reserved. This is inferred and needs a test.
- Evaluation ordering at `execution_ledger.py:810,1561` lacks the `rowid` tiebreak used at `:400`. Align them.
- `maf_supervisor.py:451`: the error text still says "v5, v6, or v7".
- Tampering tests mutate one field each (`diff_digest`, `reason`). Add per-field cases for `action_id`, `verifier_input_digest`, `raw_output_digest`, `test_evidence_digest`, and the receipt `verifier_usage` counters.

### Requirement Fit

- **AC1:** The completion gate is correct in code (gateway `:969-971`, contracts `:854-858`), but a real provider cannot reach it (Critical 1).
- **AC2:** Met. The candidate is kept in the evaluation, and handback never succeeds.
- **AC3:** Met after fix 2 for the evaluator classes. Provider-supplied hashes are never trusted. Adapter-level mismatch remains open (Important 4).
- **AC4:** Partly met. The durable order is correct (input, send, response, complete, evaluate). Adapter faults become `unknown`, and resume does not re-evaluate (Important 3 and 4).
- **AC5:** Met. `BEGIN IMMEDIATE` decides under a lock, the cap is checked before the retry rule and before the global budgets, the count is shared across verifier identities, unknown sends consume allowance, and not-dispatched releases it. A third proposal is denied before the adapter is called; the test asserts the send list.
- **AC6:** Partly met. Maximum, reserved, consumed, and denied counts are reported and recomputed. The evaluation itself is not recomputed (Important 5).
- **AC7:** Met. The existing pre-evidence denial and producer/verifier separation still apply.
- **AC8:** Met. Branches are v8-only, v7 fixtures are unchanged, and migration uses additive `CREATE TABLE IF NOT EXISTS`.
- **AC9:** Mostly met. Replay re-evaluation, adapter-level mismatch, and prompt-contract presence are uncovered.
- **Scope drift:** None material. The requirements' tension between "retries" as a non-goal and "one automatic retry" was resolved in `solution.md` as a Magentic-proposed retry, and that was approved. Narrowing "fail requires a finding" to "fail requires a blocking finding" matches ADR 0015.

### Validation Fit

- Coordinator runs used `python3.12`; the system `python3` is 3.9 and cannot import `cli/fsutil.py`:
  - Focused suites (`test_verifier_contracts`, `test_structured_verifier_ledger`, `test_chartered_delivery_gateway`, `test_chartered_execution_contract`, `test_maf_delivery_lead`): 55 tests passed.
  - Full suite (`python3.12 -m unittest discover -s tests`): 1353 tests passed, 0 skipped. `validation-results.md` reported 1 skipped; the difference is environmental.
  - `git diff --check`: clean.
- Test strength is good where coverage exists. The concurrency test forces a real race with `threading.Barrier`. The pre-send denial tests assert that the adapter was not called.
- The central integration claim, that a real verifier returns the contract, has no evidence. Deferring the live run was reasonable, but it hid Critical 1.

### Residual Risks

- Even with a contract prompt, strict parsing may make Ollama output often `unusable`. A controlled live job, which AC10 allows, is advisable once Critical 1 is fixed.
- Receipts are self-sealed with unkeyed digests. Tamper evidence is only as strong as recomputation, and that is a pre-existing design limit.

## Disposition

- **Needs refinement.** Return to implementation for Critical 1 and Important 3, 4, and 5. Important 2 was fixed in this lane and is awaiting commit.
- Run state stays `reviewing`. `accept-review` was not run. Nothing was published or merged.

## Acceptance Review (after refinement)

Reviewed 2026-09-23 on the final branch: `origin/main..HEAD`, including the refinement commits and the AC8 fix below. The verifier assignment was `acceptance-quality`, and the proof review was `acceptance-test`. Both reports are in `research/`. The orchestration manifest now declares both producers: the original implementation and the refinement.

### Verdict

- **Ready to accept.**

### Findings

- **Critical (found and fixed in this round):** a round-2 refinement change broke AC8. Completed v6 and v7 receipts raised `KeyError: 'verifier_evaluations'`, because the final-evidence check sat outside the v8 guard. The quality reviewer found it. A new regression test reproduced the exact `KeyError` before the fix and passes after it. The reviewer re-checked the fix and accepted.
- **Important:** none open.
- **Suggestions (deferred):**
  - Add a direct test for the stale-evidence gate.
  - Test attempt inspection on a stored v7 receipt.
  - Record truncation of output over 64 KiB.
  - Add tests for `num_predict`, the `rowid` tiebreak, and the supervisor message.
  - Assert AC5 cap denial with the global budgets explicitly non-exhausted.
  - The Codex and Claude adapters don't pass `provider_task`. Neither is an approved verifier today.

### Requirement Fit

- **AC1–AC8:** met.
  - The verifier input carries the Flow output contract.
  - Observation comes before evaluation, received faults are `unusable`, and replay re-evaluates.
  - The cap is enforced before send.
  - Receipts recompute each evaluation and bind it to the evidence.
  - v6 and v7 receipts keep their original semantics.
- **AC9:** met. See `research/acceptance-test.md`.
- **AC10:** met. No live run was required.
- **Scope drift:** none. The only additions beyond the plan are the round-2 hardening and the AC8 fix, both inside this slice.

### Validation Fit

- The full suite at the final change set (`python3.12 -m unittest discover -s tests`) passed 1370 tests, with 0 skipped. `git diff --check` is clean.
- Mutation checks are recorded in the `validation-results.md` addendum: five checks, each caught by its intended test. The AC8 regression test was also shown to fail before its fix.
- The reviewers read the code only. The coordinator ran every suite.

### Residual Risks

- A v8 attempt that crashes cannot be resumed. The replay re-evaluation and stale-evidence paths guard future resume support, but a crash today leaves the attempt `started`, which needs operator reconciliation.
- Real verifier output hasn't been tested. A controlled live Ollama run is advisable before production reliance.

