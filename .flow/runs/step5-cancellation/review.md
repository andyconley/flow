# Acceptance Review: step5-cancellation

**Scope:** `62a4d5f..b066309` (implementation and implementation-review fixes), plus the review-refinement commit that this review adds. It is judged against `requirements.md` (R1–R10, the reason-code table), `acceptance-criteria.md` (AC1–AC12) and `plan.md` (D1–D7).

## How the review ran

- **Coordinator:** read the requirements, the acceptance criteria and the plan head. Read the ledger seal diff, `build_terminal_receipt`, `abandon_delivery`, `stop_on_cancel` and `reap` directly. Ran the three new test modules twice: 67 tests, OK both times, 28.5 s each, no flakiness. Ran the full suite at `b066309`: 1,638 tests OK, 0 skipped, with `FLOW_MAF_PYTHON`.
- **quality-reviewer** (opus):
  - Verdict: ready, with one Important finding about operator guidance.
  - It confirmed that R1–R10 and every reason code are implemented without drift.
  - It found the seal atomic and fenced, and the cancel races keyed on the flag.
  - It found the lock order consistent with ADR 0016, and no path that resends or reclassifies an uncertain send.
  - It verified every Q-, Qs- and S-series disposition in the code.
- **test-engineer** (sonnet):
  - Verdict: pass.
  - Every sampled AC bullet has a falsifiable oracle. For example, AC1 guards against an empty group list, AC4 checks every generation by `(generation, kind, action)`, and AC10 compares every file before and after, byte for byte.
  - Tests are hermetic: FIFO or file sync, bounded deadlines, no live calls.
  - The Linux and pidfd gaps are honestly labelled.
  - It had no shell, so the coordinator ran the tests (above).
  - Advisory expertise: `no_match` (request `210ed529-ef1d-4d53-adc9-be188dbd9e38`), so nothing was delivered and there is no disposition.
- **security-reviewer** (opus):
  - Verdict: pass, with two Important findings.
  - Every S-series fix is present and correct.
  - It found no path traversal, and the killpg bounds hold.
  - The pidfd ordering is correct.

## Findings and dispositions

| # | Source | Finding | Disposition |
|---|---|---|---|
| RS-I2 | security | `reap` caught only `ProcessLookupError`. An EPERM from `killpg` or `kill` (a setuid member, or a changed uid) escaped. That stopped an abandon partway through, and in `stop_on_cancel` it crashed the live parent before the seal or interruption. | **Fixed.** Both kill sites report `skipped_permission`. `stop_on_cancel` reports a failed reap as `reap_failed` and still seals or records the interruption. Tests: `ReapTests.test_a_refused_signal_is_reported_and_the_reap_goes_on`, `ReviewRefinementTests.test_a_failed_reap_still_records_the_interruption`. |
| RS-I1 | security | ADR 0019 claimed a tamper defence ("older than its recording parent"), but that floor comes from the same editable record. `reap` also lacked the caller-group and leader-uid checks the ADR listed. | **Fixed.** `reap` skips the caller's process group, and skips a leader another user owns (`skipped_other_user`). ADR 0019 now says the checks guard honest records against reuse, and that tamper resistance rests on `.flow` being unwritable to workers. Ledger-mirrored registration stays a follow-up. Tests: `test_a_leader_owned_by_another_user_is_never_signalled`, `test_the_callers_group_is_never_signalled`. |
| RQ-I1 | quality | After a cancel or abandon, a producer's partial edit stays in the worktree, and a successor's prepare refuses it. Nothing tells the operator. | **Documented** in ADR 0019 Consequences: reset to `source_commit` or use a fresh worktree. An `inspect-delivery` baseline-drift hint and an editing-stub AC7 variant go to the backlog. |
| RQ-S1 | quality | Stale lock-order text (`abandon_delivery` docstring, ADR 0019 lines 31 and 79) after the Q4 and Qs1 fixes. | **Fixed.** |
| RQ-S3 / RS-S2 | quality, security | A cancel request left by a killed CLI could turn a later stray SIGTERM into `cancelled`. A CLI timeout can report `cancel_timeout` for an attempt that did seal. | **Partly fixed.** A dispatching parent removes any request it finds before it records itself. Test: `test_a_request_left_before_the_parent_recorded_itself_is_cleared`. The remaining in-run window and the timeout misreport are documented as ADR 0019 residuals. |
| RQ-S4 | quality | `stop_on_cancel` caught only `LockDeadline` and `ContractError`, so an `OSError` or `sqlite3.Error` skipped the interruption fallback. | **Fixed.** Both excepts are widened. |
| RQ-S7 | quality | An `allowed` manager call stays `allowed` in a cancelled receipt. | **Documented** in ADR 0019 (it was never sent; the same holds for the superseded seal). |
| RQ-S2 | quality | `evidence.edit`, `evidence.tests` and `verifier_input_sha256` are always null in a terminal receipt. | **Accepted.** `verifier_inputs` carries the digests. Backlog: fill `edit` from `repair.diff`. |
| RQ-S5 | quality | The abandon recreate path makes the directory before taking the fences. | **Accepted.** At worst an empty private directory is left behind, and a retry uses it. |
| RQ-S6, S8, S9 | quality | A pre-`Popen` cancel check; the MAF `finally` kills the group only while the leader lives; the prepare-to-lock window. | **Accepted.** In every case nothing is resent, and abandon reaps any survivors. |
| RS-S1, S3–S7 | security | Member list-then-kill reuse window; `stuck` reads `run.json` unbounded; abandon's blocking `run_lock` and `send_lock`; FIFO check on `groups.jsonl`; `exists` vs `lexists` on `.closed`; attempt-id cross-check; machine-id host-name fallback. | **Accepted for the single-user threat model.** Each needs write access to `.flow`, or a busy Linux host. Promoted to the backlog as one hardening item. |

## Review Summary

### Verdict
- Ready to accept.

### Findings
- **Critical:** none.
- **Important:** RS-I2 and RS-I1 are fixed in the refinement commit. RQ-I1 is documented.
- **Suggestions:** dispositioned above. The ones that remain go to the backlog.

### Requirement Fit
- R1–R10 and the reason-code table are implemented as specified, with no scope drift, as independently confirmed by the quality review.
- The success criteria are met in hermetic form:
  - cancelling a blocked provider call within the deadline;
  - the dead end and a runtime-cap interruption, each followed by abandon and a completed successor;
  - `stuck` naming the exact next command;
  - no resend or reclassification.
- One caveat: RQ-I1. A successor needs a clean worktree, which the tests don't exercise because their stubs never edit.

### Validation Fit
- The AC→test map in `validation-results.md` was spot-checked against real assertions.
- The full suite was re-run by the reviewer: 1,638 OK, 0 skipped at `b066309`; 1,643 OK, 0 skipped at `a16fea4` (the refinement fixes). `regenerate-flow-help.py --check` is up to date. The new modules are stable across two runs.
- Mutations M1–M6 are taken from `validation-results.md`. The five refinement tests were each shown to fail with the fixes reverted.

### Residual Risks
- The Linux `/proc` reader is parser-tested only, and pidfd is not exercised.
- The microsecond window on macOS between the re-check and the signal.
- Tamper resistance depends on `.flow` being unwritable to workers.
- The in-run stale-request window and the `cancel_timeout` misreport.
- Real Codex, Claude and Ollama are unexercised until `v8-live-validation-3`.

## Acceptance gate

`flow run validate-orchestration step5-cancellation --stage acceptance` fails with `writable-producer-binding`:
- `research-live-child`, `research-abandon-seal` and `research-shaper-authority` are writable, and each wrote its `research/*.md` note;
- but `verification.producer_assignments` lists only `definition-root`.

The truthful fix is to add those three to `producer_assignments`. The verifier, `adversarial-architecture`, stays distinct. But `orchestration.json` is a sealed definition artifact (`approved_artifact_digests.orchestration_manifest`), so Andy made that amendment himself on 2026-09-27. After it, the acceptance validation passes. The approved digest in `run.json` still records the definition-time manifest; this amendment is the only change.
