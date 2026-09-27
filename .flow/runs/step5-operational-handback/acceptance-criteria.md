# Acceptance Criteria: step5-operational-handback (revision 2)

All criteria are hermetic:
- stub providers return scripted outputs and usage;
- the real gateway and ledger are used;
- end-to-end criteria run the pinned stock Magentic runner with stubs;
- no paid or live calls are made.

Terms:
- **Charged** means `charged_v1` (P1).
- **The fixture lineage** is one v8 work id made of:
  - an attempt with an `unknown` paid send, abandoned;
  - a successor that completes after one automatic token tranche, one engineer-decided escalation resumed in answer mode, and a D5-style recovery.

## Trace correlation

- **AC1. Manager identity.** A completed Claude manager row carries `session_id`, `input_sha256` and `num_turns`, and a Codex manager row carries `thread_id`. `validate_receipt` rejects a completed manager row that is missing its adapter-required identity field.
- **AC2. Manager request files.**
  - Every manager call that was ever `allowed` has `manager-requests/<call_id>.json`, containing exactly `{call_id, prompt_digest, messages}`, with mode 0600. `digest(messages)` equals `prompt_digest`.
  - The file exists before `consume_manager_grant`. A fault injected between the write and consume leaves the file in place and the row `allowed`.
  - A fault injected mid-write leaves no file at the final path.
  - A digest mismatch refuses the send before any provider call.
  - A replay of a never-sent grant reuses the identical file.
  - A pre-existing file with different bytes refuses the send and is left unchanged.
  - For Claude, `sha256(render_manager_prompt(messages))` equals the observed `input_sha256`.
- **AC3. Grant history.**
  - **Coverage is structural.** A test enumerates every write to `grant_id`, and every status transition away from `allowed`, in `execution_ledger.py`, by parsing the source. It asserts that each is covered by a test that sees exactly one `grant_changed` event with the right `op`.
  - **Replay.** For a row that was granted, released, regranted after recovery and consumed, the `grant_changed` events alone reproduce its ordered history.
  - **Old details are unchanged.** The existing events' `detail` strings are unchanged, so the tests that match them pass unmodified.
- **AC4. Process groups.** A provider group line carries the id of the call it served. The MAF and test lines carry `null`.
- **AC5. Checkpoint parent.** Each link records `previous_checkpoint_id` equal to the file's value, including after a recovery that quarantines checkpoints.
- **AC6. Recovery actor.**
  - Without `--actor`, `recover-delivery-lead` exits non-zero before any change.
  - With `--actor X`, the recovery row and the owner actor record `X`.
  - `codex-assisted-recovery` no longer appears in `cli/`.
- **AC7. `flow run trace`.**
  - **Banner, paused.** For an attempt paused on `token_cap`, the first line is a golden-pinned banner. It names the reason, the seq and time, the row and the exact next command.
  - **Banner, terminal.** For a terminal attempt, the banner shows the status, the cause and the receipt digest.
  - **Rows.** On the fixture lineage there is one row per manager call and action, in seq order, with every R7 field and the expansions interleaved.
  - **Durations** equal the differences between event timestamps.
  - **Totals** show absolute charged, cap, remaining and headroom tokens, and they equal R9.
  - **Stable JSON.** The JSON schema is pinned.
  - **Read-only.** Every file is byte-identical afterwards.
  - **Unsupported attempts.** A v5–v7 attempt prints `unsupported_protocol`.
  - **Missing work id.** A missing work id exits non-zero.

## Token cap

- **AC8. Contract.** Each of these is refused:
  - a missing token field;
  - a non-positive token field;
  - `token_tranche < unobserved_send_tokens`;
  - `unobserved_send_tokens > max_lineage_tokens`;
  - headroom above `MAX_TOKEN_TRANCHES`;
  - `max_lineage_tokens + headroom × tranche > MAX_LINEAGE_TOKENS`.

  Also:
  - The charter and the envelope project the fields exactly.
  - An envelope built from an older charter is refused at prepare.
  - The shipped default intent uses the P10 values.
- **AC9. Charging.** A table test of the pure `charge` function covers:
  - Claude, with disjoint cache fields;
  - Codex, with `cached_input_tokens` ⊂ input;
  - Codex, with an extra unknown key (ignored);
  - an `unknown` row, a `started` row, and a `failed` row without usage (each charged `unobserved_send_tokens`);
  - a completed paid row with an unrecognised shape (charged the sealed amount, `recognised: false`; the call completes and is not marked unknown);
  - `allowed`, `denied` and `not_dispatched` rows (0);
  - Ollama (not charged, reported under `verifier_tokens`).

  The fixture values come from captured real usage (see the open questions).
- **AC10. Refusal on each path.** With no headroom and charged ≥ cap:
  - **Initial grants.** The next paid action grant and the next paid manager grant are refused with `token_cap` before any send.
  - **Regrant and reissue.** Each regrant and reissue path makes a hard `token_cap` denial with the documented state change.
  - **`reissue_recovered_manager_grant`** also enforces the call and round caps, excluding its own row. When it is denied, the attempt fails, and the grant events show `op=deny`.
  - **Unpaid calls.** An unpaid manager and the Ollama verifier are still granted.
- **AC11. Just under the cap.**
  - With charged = cap − 1, the grant is allowed.
  - Once the call is observed, the next grant is refused.
  - The receipt's `overshoot` equals the actual excess.
- **AC12. Tranche expansion.**
  - **Automatic grant.** With one tranche of headroom, the first `token_cap` hit is granted as `charter_headroom`. The effective maximum rises by exactly `token_tranche` tokens, and the replayed call is the one sent.
  - **Escalation.** The second hit pauses for `decide-expansion`, with no manager or paid send between the pause and the decision, measured by seq. An engineer grant then resumes the attempt through `recover-delivery-lead` in answer mode.
- **AC12b. Shortfall of more than one tranche.** A single observed call that leaves `charged − effective ≥ token_tranche` makes the next grant a hard `token_cap` refusal, on both the automatic path and the engineer path. No expansion request is created.
- **AC12c. Concurrent overshoot bound.**
  - With `max_concurrent` = 2 and charged just under the cap, two paid action grants are allowed before either is observed.
  - After both are observed, the next grant is refused.
  - The receipt's `overshoot` is at most the sum of those two calls' charges, and it matches the R12 statement.
- **AC13. Lineage.**
  - A successor's gate counts the abandoned predecessor's `unknown` send at its sealed charge.
  - `lineage_usage.predecessor_charged` equals that sum.
  - A superseded predecessor with no receipt is still charged.
- **AC14. Receipt block.**
  - `validate_receipt` recomputes `token_usage` from the rows plus `lineage_usage`, and rejects an edit to any field of it.
  - Both seals refuse a block that differs from R9.

## Receipt verification

- **AC15. Clean pass.**
  - On the fixture lineage, `verify-receipt` exits 0.
  - Every V1–V17 check is `pass` with `compared ≥ 1`, or `not_applicable` exactly where the R14 table allows, with its fixed reason.
  - Every R15 item is `unverifiable_offline`.
  - The predecessors are verified recursively, and `--no-lineage` skips them.
- **AC16. Tamper specificity.** Each tamper case is applied to a copy of the fixture and declares its exact expected set of failing checks. The test asserts that exact set: those checks fail, and every other check keeps its clean status. Each failure detail names the row or field and both values, or both digests plus the first differing key path.

  | Tamper | Expected failing checks |
  |---|---|
  | Byte-only receipt change (whitespace) | {V1} |
  | Receipt content change | {V1, V3} |
  | A ledger action's result content changed, same status | {V3, V4, V17}. V4 and V17 fail only when usage was changed; the table records which case applies. |
  | Envelope limit changed | {V2, V7} |
  | Charter file byte changed | {V7} |
  | Requirements snapshot changed | {V8} |
  | Checkpoint byte changed | {V9} |
  | Request file message changed | {V10} |
  | `repair.diff` byte changed | {V11} |
  | Trace byte changed | {V14} |
  | `baseline.json` field changed | {V13} |
  | Duplicated `manager_send_started` event | {V15} |
  | Predecessor receipt byte changed | {V6} |
  | Group line row id changed | {V16} |
  | A `grant_changed` event deleted | {V15, V17} |

  The planning step may correct an expected set only by recording why in `validation-plan.md`.
- **AC17. No vacuous pass.**
  - A completed attempt whose ledger has no action rows fails V3.
  - A missing `repair.diff` on a completed attempt fails V11.
  - An empty checkpoint directory that is referenced fails V9.
  - A supported attempt whose receipt is missing `token_usage` fails, with exit 1. It is not reported as `unsupported`.
  - An attempt that isn't sealed gives `attempt_not_sealed` (exit 2).
  - A pre-release contract version, read from the ledger envelope, gives `unsupported_receipt` (exit 2).
- **AC18. Read-only and offline.**
  - Every file under the run directory is byte-identical afterwards, including lock files.
  - The ledger connection is read-only, and reads happen in one transaction.
  - With subprocess and socket calls patched to raise, the verifier completes, which proves it makes neither kind of call.
- **AC19. Cancelled and abandoned.** Verification passes on a `cancelled` fixture and on an `abandoned` fixture, following the requiredness table:
  - V5 requires `termination`;
  - V11–V13 are `not_applicable` with their fixed reasons, where no edit ran.

## Seal

- **AC20. Full-row seal.**
  - `finish_attempt` refuses when one action row's result content differs from the ledger with the same status. It also refuses for one manager call row, and for an added or removed row key.
  - `seal_terminal_uncertain` refuses the same.
  - The receipt is built from a snapshot taken under the sealing `send_lock`, after `close_expansions`.
  - A single comparison function is imported by both seals and by V3.

## Docs and regression

- **AC21. Docs.**
  - ADR 0020 covers every item in R17, including the R12 statement and the P10 derivation.
  - The design doc's step 5 is updated.
  - `regenerate-flow-help.py --check` passes.
  - The CLI reference covers `trace`, including the `--json | jq` note, `verify-receipt` and `--actor`.
- **AC22. Regression.**
  - The full suite passes with `FLOW_MAF_PYTHON`, with 0 skipped.
  - The existing expansion, recovery, cancel and abandon tests pass. Their fixtures change only to add the token fields, the actor argument,. Each such change is listed in `validation-results.md`.
- **AC23. Supersedes the hand check.**
  - `validation-results.md` confirms the mapping in `reconciliation.md` from each generic `receipt_check.py` check to a named V or trace check.
  - It runs `verify-receipt` and `trace` on the fixture to show each mapped item.
