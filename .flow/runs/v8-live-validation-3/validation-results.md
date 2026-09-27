# Validation Results: v8-live-validation-3

- **Installed CLI:** v0.38.0, the sealed release. v0.38.1 appeared before launch but contains only docs (`git diff --stat v0.38.0 v0.38.1 -- cli runtime scaffolds` is empty), so it wasn't installed.
- **Charter:** v3 `756f6503…2b98`, sealed at `start-plan` on 2026-09-27.
- **Job commit:** `d6d771f2eccdcdd4a0ab43b9691b8cf8f92823a2` on `job/decide-expansion-docs-2`.
- **Job charter sha256:** `fef217325168cf4fbe378f605a006d4315bbebb98af106cd7e9c8ce943fdf798`, byte-identical to run 2's.

## Outcome

**One attempt, which sealed `completed`.** This is the first completed live v8 chartered job. The primary outcome is met: the full v8 chain ran end to end on real providers, including an automatic grant, an escalation decided by Andy, and an answer-mode resume, and it sealed a valid receipt. The secondary documentation change is also delivered.

- **Attempt 1:** `def92b2b2bdb4fe0a40c426edba56bd7`.
- **Receipt:** `execution/def92b2b…/receipt.json`, sha256 `0ec8bf30493ce9de95348931899d7f59ae48da58108b2b29f07ca39ff47cd459`. This matches the ledger's `sealed_receipt_sha256`.
- **Wall time:** 128 s for launch 1, which ran until the pause. Andy's decision took 190 s. Recover 1 took 7 s. The whole attempt took about 5.5 minutes.

## Preflight and preconditions

Recorded in `evidence/preflight.txt`, `evidence/baseline-test.txt` and `evidence/verifier-gate.json`:
- `gemma4:26b` was listed, warmed, and loaded on 100% GPU with UNTIL `Forever`.
- Claude was logged in.
- The specialist digests `9daf3e0f…` and `1ee52e24…` equal the sealed ones.
- The MAF import was OK.
- `validate-orchestration --stage dispatch` was valid before launch (recorded in `preflight.txt`). It also ran and passed before recover, in the same shell command, but its output wasn't saved. For decide there is no separate record: `decide-expansion` runs the orchestration check itself (`delivery_gateway.py:1106`) and returned rc=0.
- The worktree was clean, including untracked files, at `d6d771f2`.
- `flow run stuck` listed nothing for this work id.
- **Baseline:** the targeted test failed 2 of 3 before the run (A8), shown by `FAILED (failures=2)`. The file shows only the last FAIL traceback, and `rc=0` there is the exit status of the `tail` pipe, not of the test.
- **Verifier gate:** `go` in **4.95 s** against a 30 s limit, with valid schema JSON.

## Timeline and per-call timings (`evidence/attempt-1-timings.txt`)

| # | Call | Duration | Notes |
|---|---|---|---|
| 1 | manager 1 (facts) | 24.34 s | |
| 2 | manager 2 (plan) | 9.96 s | |
| 3 | manager 3 (progress) | 15.44 s | selected `docs-editor` |
| 4 | producer: Claude edit | 47.18 s | `flow_observed_claude_cli_completed_turn` |
| 5 | manager 4 (progress) | 15.65 s | selected `local-verifier`; its reply was repaired (D4) |
| 6 | verifier: Ollama | 7.04 s | `valid_pass` |
| 7 | manager 5 (progress) | 7.61 s | **granted automatically** (`charter_headroom`, 0.0 s wait) |
| — | manager 6 (final) | — | **escalated**, and the attempt paused as `expansion_paused` |
| — | Andy's decision | 190.15 s | approved (`engineer`) |
| 8 | manager 6 (final, after resume) | 6.51 s | answer-mode resume, sent once |

## Decision and resume (AC5, AC6)

- **Pause.** Captured in `evidence/status-pause-1.txt` and `inspect-pause-1.json`.
  - The next action was `decide expansion exp-bff0f248… (--expected-generation 1)`.
  - Headroom left: manager 0, paid 1, verifier 1, delegations 1.
  - No manager send was made while paused. `receipt-check-1.txt` (`AC5_AC6_escalated_call_identity`) asserts it from the ledger event times: 5 `manager_send_started` events before the pause (20:12:25.27), 0 between the pause and Andy's decision (20:15:35.41), and 1 after.
- **Decision** (`evidence/decide-1.json`): `decide-expansion … --approve --expected-generation 1 --actor andy --explanation "approved"` returned `granted`, with grant `expg-bff0f248…`. `inspect-after-decide-1.json` shows the expansion status as `closed`.
- **Resume** (`evidence/recover-1.json`): `recover-delivery-lead` ran in `mode: answer` and returned `completed`. Before it, the re-warm, `ollama ps` (`Forever`) and interpreter check ran in the same shell command, but their output wasn't saved to a file. No verifier call followed the resume.
- **Replay identity** (`evidence/receipt-check-1.txt`):
  - manager sequences 1–6 are contiguous;
  - there were 6 `manager_send_started` and 6 `manager_response_observed` events;
  - `adapter_send_started` fired exactly once for each action (editor 1, verifier 1);
  - completed calls were replayed from the ledger, with no second send.
- **Call identity:**
  - The escalated request's `denied_row_id` `6780598c…` is the call id of the completed manager call 6, which completed exactly once.
  - The automatic grant's `consumed_by` `e0fc77f5…` is call 5.
  - Both are asserted in `receipt-check-1.txt`.
- The paused call was **not** a D4 retry. It was the final call, and the D4 repair was on call 4. The repair added no send (6 calls, 6 sends), so the escalation stayed at call 6.

## Receipt checks (`evidence/receipt-check-1.txt`, `scripts/receipt_check.py`)

- `validate_receipt`: **pass**.
- The sealed sha256 matches the file.
- The envelope's `expansion_headroom` is `{delegations: 1, manager_calls: 1, paid_worker_calls: 1, verifier_calls: 1}`.
- The roster is `docs-editor` (Claude sonnet) and `local-verifier` (Ollama `gemma4:26b`), and there are no predecessors.
- **Action evidence levels:** editor `flow_observed_claude_cli_completed_turn`; verifier `flow_observed_local_http_response`.
- No `local_stub` or `local-stub` appears in the receipt, in the ledger events, or in any of the 31 attempt files. The one exception is `acceptance.snapshot.md`, which quotes the criterion itself.
- **Expansion:** `exp-22aefb88…` granted with authority `charter_headroom`, and `exp-bff0f248…` granted with authority `engineer`.
- **`manager_progress`:** `repaired: [de3c7f24… (call 4)]`, `unparsable: []`.
- **Receipt evidence:**
  - the edit touched the four allowed files (diff `922ac8d8…`);
  - tests `passed`;
  - diagnostic trace 42,150 B; event trace 558,305 B.

## AC11: the documentation change (`evidence/ac11-checks.txt`, `evidence/attempt-1-worktree.diff`)

- The diff touches only the four approved files, adding 17 lines.
- The targeted test passes, 3 of 3.
- `regenerate-flow-help.py --check` reports both files up to date.
- `tests/test_flow.py` passes in the worktree (730 tests OK).
- **Diff review, on the merits:**
  - The TOML entry keeps the raw `|`, and the two table rows use `\|`, placed right after `inspect-delivery`. The summary matches the style of neighbouring rows.
  - The `cli-reference.md` section gives the exact syntax and the five refusal classes. It says a refusal changes nothing, and that a decision doesn't resume the attempt: `recover-delivery-lead` does.
  - One inaccuracy. The section says `--expected-generation` "must match the attempt's current owner generation". That is right for the ledger attempt generation. But elsewhere the docs call the lead generation the "owner generation", so the phrase is ambiguous. That matches the existing code wording and isn't a blocker. It can be tightened in the docs PR.
  - The change is ready to merge as real documentation.

## AC12: the earlier fixes hold live

- **D1:** the editor turn ended with a terminal `result` event observed by Flow. The event log is 558,305 B, 0.53× the old 1 MiB cap. It contains 0 `stream_event` records, and no limit errors occurred.
- **D3:** the verifier returned non-empty, schema-valid content in 7.04 s.
- **D4:** call 4's malformed progress reply was repaired, as recorded in `manager_progress`. The attempt continued. This is the first live exercise.
- **D5:** `recover-delivery-lead` succeeded in answer mode after the `charter_headroom` grant at call 5.
- **D6:** not exercised, because no no-edit turn occurred.
- **D7: met through a substitute.**
  - The AC wording ("request messages in the ledger") can't be checked as written. The ledger's `manager_calls` rows store request metadata and a `prompt_digest`, not the message text.
  - The substitute is the Magentic checkpoints, which hold the Flow-built task every manager prompt is built from. The facts line "The approved editors get one call in total" is in all 13 of them: the 6 live checkpoints, and the 7 quarantined by recovery `6426ff31`. That includes the initial task message that feeds manager call 1, where the line sits inside a base64 pickled message.
  - The checkpoint files weren't checked against their `magentic_checkpoint_links` digests.
  - **Observation:** the editor delegation asked for the complete edit in a single turn.

## Verdicts

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | **Met.** A v3 charter `756f6503…` (preflight). The R1 limits and headroom are in `delivery-charter.json`, and `inspect-delivery` shows them in `inspect-pause-1.json` and `inspect-final.txt`. `delegated_expansion: true` is in `shaper-contract.json`. | as listed |
| AC2 | **Met.** Protocol v8, the exact headroom map, the roster and a Claude manager, and the worktree clean at `d6d771f2`. | envelope, preflight |
| AC3 | **Met.** Every call is physical Claude or Ollama evidence, and there is no stub. | receipt-check-1 |
| AC4 | **Met, for the first time live.** Manager call 5 was granted from `charter_headroom` with no pause. | timings, receipt |
| AC5 | **Met.** An escalation at call 6, `expansion_paused` with nothing sent, the status next action, and Andy's decision. | pause and decide evidence |
| AC6 | **Met.** Answer-mode resume, contiguous sequences, one send per call and action, and it wasn't a D4 retry. | receipt-check-1 |
| AC7 | **Met.** `validate_receipt` passes, the sha256 matches, and the expansion block is complete. | receipt-check-1 |
| AC8 | **Met: `completed`.** The diff and passing test were observed by Flow, then a valid verifier pass. | recover-1, receipt |
| AC9 | **Met.** Everything is listed above. The timings come from ledger events, with none missing. | this file, `evidence/` |
| AC10 | **Met.** One attempt, with no successor needed. Nothing was staged. | commands.txt |
| AC11 | **Met.** See above. | ac11-checks |
| AC12 | **Met.** D1, D3, D4 and D5 held. D7 is met through the checkpoint substitute (the AC wording can't be checked, because the ledger stores digests only). D6 was not exercised. | above |
| AC13 | **Not applicable.** The attempt sealed on its own. `stuck` lists nothing for this work id before launch or after the seal. | `preflight.txt`, `stuck-after-seal.json` |

## Observations and gaps

- **Exit codes.** `execute-chartered-job` exiting with rc=1 on `expansion_paused` (`commands.txt`) is the documented behaviour for a pause, not an error.
- **Recovery actor.** The receipt's recovery actor is `codex-assisted-recovery` in a Claude-only run. It's a hard-coded default (`delivery_gateway.py:1132`), and the provenance is misleading. To be recorded as a capability gap.
- **Receipt checker.** After acceptance review, `receipt_check.py` was hardened:
  - a missing event log or checkpoint set now reports "could not run", and an absent pause or decision time reports an error, instead of a silent or vacuous pass;
  - the stub scan now covers the ledger events and every attempt file;
  - it asserts the call identity and the send counts within the pause window;
  - it decodes base64 checkpoint content.

  The evidence was re-recorded.

- **Receipt-check script.** Two field paths in the first draft were wrong: the grant authority, and where the D7 facts live. Both were corrected in the script and the evidence was re-recorded. Neither was a Flow defect.
- **Timings.** `inspect-delivery` still doesn't show per-call timings, so a script was needed again (gap `delivery-per-call-timings`).
- **D7 checking.** The manager's conversation text is visible only in the checkpoints, not the ledger, so D7 had to be checked from checkpoint files.
- **Evidence hygiene.** The Claude CLI's `latest` symlink was removed from the attempt directory before commit.
