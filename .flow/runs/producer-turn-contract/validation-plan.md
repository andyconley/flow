# Validation Plan: producer-turn-contract

| AC | Proof |
|---|---|
| AC1 | `_execution_facts` parameterized over protocols 6, 7 and 8: the one-call phrases, and a block of at most 1,500 bytes |
| AC2 | Protocol 5's facts are byte-identical to today's |
| AC2b | A fake supervisor receives a task that contains the line |
| AC3 | Four direct `_verify_chartered_edit` cases: (a) clean, (b) out of scope, (b) deletion, (c) declared regression with no edit |
| AC4 | A chartered attempt with a no-edit producer fails with "editor made no edit to the worktree" |
| AC5 | The doc diff contains the sentence |
| AC6 | The full suite is OK with 0 skipped (with `FLOW_MAF_PYTHON`), and M1–M4 are each caught |
| AC7 | No paused or interrupted attempt is found before merge |

Live proof is out of scope. `v8-live-validation-3` checks that a real manager delegates a single editing turn.
