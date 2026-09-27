# Implementation Review: step5-cancellation

**Scope reviewed:** commits `5bf826b`, `0973be1`, `1632044`, `1050db2` and `ac3aa4c`, on top of the plan commit `62a4d5f`. Reviewers read the diff from `research/impl-diff.patch`. The fixes are in commit `b066309`.

## Roles

- **quality-reviewer** (opus). Verdict: needs refinement; nothing critical. 4 important findings, 13 suggestions.
- **test-engineer** (sonnet). Verdict: the proof is strong and built on real oracles. The one "critical" item questioned the M2 mapping.
  - Expertise lookup: **admitted** (request `05ed1e84-89b9-4c7e-8131-1e2605ca9ec1`), with entry "Define a test oracle with a concrete example".
  - The role reported it as applied, `trigger_satisfied`, with evidence codes `ac1_map_row` and `m5_prediction`. The disposition is recorded (post-receipt `d3b78b53…`).
- **security-reviewer** (opus). Verdict: safe for the single-user threat model once the FIFO hang is fixed. 2 important findings, 7 suggestions.

## Findings and dispositions

| # | Source | Finding | Disposition |
|---|---|---|---|
| Q1 | quality | R5 gap: an absent attempt directory is refused instead of created. | **Fixed** (`b066309`). Abandon recreates a truly absent directory (mode 0700) for a `started` attempt of this run, and the seal records `baseline_missing`. A symlink or an unknown attempt keeps `attempt_dir_unsafe`. Test: `ReviewFixTests.test_a_lost_attempt_directory_is_recreated_and_abandoned`, with a successor that completes. |
| Q2 | quality | Cancel can SIGTERM a parent whose handler is already restored. | **Fixed, with a residual documented.** `_signal_parent` re-checks the closed marker right before signalling (the parent marks the record closed before restoring the handler). The remaining microsecond window on macOS, which has no pidfd, is recorded under ADR 0019 "Residual windows". |
| Q3 | quality | The recovery path ignored disarm. | **Fixed.** `_resume_chartered` now requires `controller.armed` before `stop_on_cancel`. |
| Q4 | quality | Abandon blocked on `run_lock` behind a live guarded send. | **Fixed.** Abandon takes `recovery_lock` (non-blocking) first, then `run_lock`, the ADR 0016 order. Test: `test_abandon_refuses_at_once_while_a_live_parent_holds_the_run_lock` (under 5 s). |
| Qs1 | quality | The receipt was written before its checks. | **Fixed.** Every comparison runs on the bytes first. Test: `test_a_refused_seal_leaves_the_earlier_draft_untouched`. |
| Qs2 | quality | Check the flag before a grant is used. | **Fixed** for the manager grant, the producer grant (whose `close_pre_send_failure` releases it), and the verifier grant (left `allowed`, which the seal releases as `not_dispatched`). Not added after a producer's grant is consumed, because that would leave a `started` row. |
| Qs3 | quality | Default generation `1` for the v8 control record. | **Fixed.** `kwargs["generation"]` is now required. |
| Qs4 | quality | A fifth next command (`inspect-delivery`). | **Documented** in ADR 0019: it applies when a recovery or decision holds the fence with no live parent. |
| Qs5 | quality | Rows can stay `started` after a hard death. | **Documented** in ADR 0019. They are just as uncertain and are counted as spent. |
| Qs6 | quality | `communicate()` with no timeout after `killpg`. | **Fixed.** Bounded to 10 s. |
| Qs7 | quality | The CLI printed tracebacks on `sqlite3.Error`; `stuck` could crash on `OSError`. | **Fixed.** Both cancel and abandon catch `sqlite3.Error`, and `stuck` records a per-attempt error row. |
| Qs8 | quality | `_lead_refusal` maps prose to codes, which is brittle. | **Accepted for now.** R8 says wrap `change_lead_claim` without changing it. Every known message maps to a code, and AC9 pins the exact outputs, so a wording change fails the tests. Follow-up: have `change_lead_claim` return codes. |
| Qs9 | quality | The docstring overclaims ("never around file writes"). | **Fixed.** The `delivery_cancel` docstring now names streamed provider trace output as the one exception. |
| Qs10 | quality | ADR wording "started after" vs "at or after". | **Fixed.** |
| Qs11 | quality | The pgid-reuse risk on the leader-gone path is undocumented. | **Documented** in ADR 0019 (R4 accepts it). |
| Qs12 | quality | `cancel_delivery` doesn't use the lock probe that R3/A8 describe. | **Documented.** Cancel relies on the recorded identity; the probe only corroborates `stuck` and `inspect`. |
| V1 | quality | AC2c: a seal-time *ledger* generation mismatch records no interruption. | **Accepted and documented.** `record_interruption` correctly refuses a stale fence; the next recovery claim records `unmarked_process_exit`. The request-generation mismatch (the reachable case) is tested. |
| V2 | quality | AC1 with a blocked provider is tested only with the lead `active`. | **Accepted explicitly.** The parent holds `run_lock` through a guarded send, so the lead cannot change then. The lead variants run between callbacks (the real MAF child), which is the case the lock-free seal (A15) exists for. |
| V3 | quality | Not verified: abandoning an attempt with an unknown verifier row. | **Verified.** `test_an_unknown_verifier_send_is_abandoned_with_a_valid_receipt` passes validation, with `verifier_usage.consumed == 1`. |
| V4 | quality | The Ollama interruptible path has no test. | **Accepted.** The same `interruptible()` wrapper is exercised through the other waits. Ollama is covered by `v8-live-validation-3`. |
| T1 | test | "Critical": M2 may not break the v7 test. | **No change needed.** The M2 actually run limits the blocker to `status='started'`, which excludes the v7 `unknown` attempt, and the named test failed, at both `ac3aa4c` and `b066309`. The reviewer had inferred a different mutation (`PREDECESSOR_TERMINAL_STATUSES`). |
| T2 | test | The dead-pid simulation uses a hard-coded pid. | **Accepted.** `2**22 + 7` is above the largest pid either OS can assign (macOS wraps below 100,000; Linux `PID_MAX_LIMIT` is `2**22`). The refusal also depends on the start time, so a live pid there would read as `mismatch`, not a false pass. |
| T3–T5 | test | Exact-string oracles; AC11 is manual; M1 and M3–M6 are confirmed. | **Accepted.** AC11 is checked manually (below). |
| S-I1 | security | A tampered record could make Flow signal a process the user owns (confused deputy). | **Fixed (the cheap mitigations).** `parent_live` refuses pid 1, Flow itself, its caller and another uid's process. Reaping, and group liveness, ignore a group whose leader started before the recording parent. Tests: `test_liveness_verdicts` (own process and init), `test_a_group_older_than_its_recording_parent_is_never_signalled`, `test_a_record_naming_flow_itself_is_never_signalled`. The stronger option (mirroring registrations in the ledger) is noted as a follow-up. Workers cannot write to `.flow` (the worktree guard plus the sandbox). |
| S-I2 | security | The probe could hang on a FIFO. | **Fixed.** The probe, `recovery_lock` and the polled flocks open with `O_NONBLOCK` and require a regular file. Test: `test_a_fifo_at_the_lock_path_never_hangs_the_probe` (probe `held`, `stuck` completes, the lock refuses). |
| S-S1/S2 | security | Unbounded reads that follow FIFOs. | **Fixed.** `read_bounded` (O_NOFOLLOW, O_NONBLOCK, regular file only, 1 MiB) for records, groups, baseline and the cancel request; trace and draft digests are streamed. |
| S-S3 | security | Run-directory components were not checked for symlinks. | **Fixed.** `.flow`, `runs`, the run and `execution` are checked, and the attempt directory must resolve inside `runs`. |
| S-S4 | security | A raw hardware id and host name are stored. | **Fixed** for the id: a `sha256("flow-machine:" + id)` digest. The host stays for display, printed with non-printable characters stripped. |
| S-S5 | security | A stale cancel request can be left behind. | **Fixed.** It is removed on any exit that doesn't end in a seal. Test: `test_a_cancel_that_does_not_seal_leaves_no_request_behind`. |
| S-S6 | security | A leader that dies before registration, and setsid escapes. | **Accepted.** Both fail safe (`skipped_unverifiable` shows in the abandon output), and processes Flow did not record are a non-goal. |
| S-S7 | security | `close()` could hide the real error on a dangling symlink. | **Fixed.** It uses `os.path.lexists`. |

## AC11 manual check

- ADR 0019 covers everything R10 lists, plus the review residuals.
- ADR 0016 carries an amendment note.
- The step 5 row and bullets in `docs/maf-adoption-design.md` are updated.
- `scripts/regenerate-flow-help.py --check` reports both files up to date.
