# Implementation Review: step5-operational-handback

- **Scope:** `be5937b..d1bcc5f` (C1–C7), plus the review-refinement commits `6106762` and `46cefbf` (RS1).
- **Reviewers:** three read-only subagents:
  - quality-reviewer (opus);
  - test-engineer (sonnet), advisory expertise `no_match` (request `81a7f846-bfa3-4c08-b058-dae03a961c09`);
  - security-reviewer (opus).
- **Checks the coordinator ran:**
  - the full suite after each commit and after the refinements;
  - 14 mutation checks (M14 added with RS1);
  - `trace` and `verify-receipt` against the real `v8-live-validation-3` run.

## Verdicts

| Reviewer | Verdict |
|---|---|
| quality-reviewer | Needs refinement: five Important findings (QR1–QR5), all in `verify-receipt` accuracy, and 13 suggestions. It confirmed that the token gate, the full-row seals, grant history, request files and V17 are sound, and match the amended plan. |
| test-engineer | Pass. Close TR1 (AC5 after quarantine) before sign-off; TR2–TR4 are minor. It judged both AC16 expected-set deviations sound. |
| security-reviewer | Pass with findings: one Important (RS1) and six Suggestions. It found no path that grants a send once the cap is reached, and no crash of the gate. |

## Dispositions

### Quality

| # | Sev | Disposition |
|---|---|---|
| QR1 | Important | **Fixed.** V11 and V12 judge an attempt that isn't completed by what it carries. A cancelled or abandoned receipt with an unbound edit is `not_applicable`. A failed attempt that edited before any verifier checks the diff and edit binding, the scope and the test command. New tests: a failed attempt that edited before any verifier, and a cancelled attempt after its edit. |
| QR2 | Important | **Fixed.** Requiredness reads the ledger snapshot and is computed inside the per-check guard. New test: a truncated receipt is reported, with V1 failing. |
| QR3 | Important | **Fixed.** A sealed attempt with a missing receipt fails V1 with exit 1, not exit 2. Test added. |
| QR4 | Important | **Fixed.** V15 reads manager sequences and expansions from the ledger snapshot. New test: rewriting the escalation authority in the receipt fails V1, and V15 still passes. |
| QR5 | Important | **Fixed.** `denied` is removed from the verifier's terminal set; such a receipt is `unsupported_receipt`. The dead line is removed. |
| QR6 | Suggestion | **Fixed.** V15(c) compares grant ids exactly in every end state. |
| QR7 | Suggestion | **Fixed.** V6 substitutes the successor's limits for a pre-release predecessor, as the ledger does. |
| QR8 | Suggestion | **Fixed.** The hard classification for `tokens` counts an approved but unconsumed tranche toward the absolute ceiling. |
| QR9 | Suggestion | **Fixed.** `_seal_attempt` refuses a pre-release v8 attempt before any draft is written. |
| QR10 | Suggestion | **Fixed.** `seal_terminal_uncertain` calls the shared `_compare_seal_locked`: derived blocks first, then rows. |
| QR11 | Suggestion | **Fixed.** A v8 `_build_receipt` requires the seal's blocks; the torn-read fallback is removed. |
| QR12 | Suggestion | **Documented.** ADR 0020 records that `token_usage` repeats `predecessor_charged`, and the own-rows scope of `cache_read_total` and `verifier_tokens`. |
| QR13 | Suggestion | **Fixed.** V17 passes, comparing one fact, when no paid grant was issued and no paid call was sent. |
| QR14 | Suggestion | **Fixed.** V10 exempts a call whose history ends in `deny` without a consume. This refines A15. |
| QR15 | Suggestion | **Fixed in part.** trace imports `PAID_PROVIDERS` and `SENT_STATUSES`. `list_request_files` is the one rule set, returning calls, temporaries and unexpected names, and V10 uses it. The small `_grant_history` and `_detail` readers stay local to each module. |
| QR16 | Suggestion | **Fixed.** The alias is inlined. |
| QR17 | Suggestion | **Deferred.** The token charge is computed twice per action decision. This is a performance cost only, bounded by lineage size; recorded as a follow-up. |
| QR18 | Suggestion | **Fixed.** The CLI reference cites `DEFAULT_TOKEN_BUDGET`. trace's text names `unsupported_contract`, and a pre-release trace test was added. `validation-results.md` is written. The mismatch between two and three leftovers is explained in the AC23 mapping: the approved requirements text can't be edited, and `reconciliation.md` gives the third. |

### Test engineering

| # | Sev | Disposition |
|---|---|---|
| TR1 | Medium | **Fixed.** The quarantine recovery test now asserts that each surviving bound link keeps the `previous_checkpoint_id` read from its file. |
| TR2 | Low | **Fixed.** The AC1 row in `validation-plan.md` names the real test file. |
| TR3 | Low | **Fixed.** The hard-coded-default search uses `rglob`. |
| TR4 | Low-medium | **Fixed before the review read it.** `test_a_pass_that_compared_nothing_fails` isolates the generic `compared ≥ 1` rule (M6). |
| TR5 | Info | **Agreed.** Both AC16 deviations narrow the tolerance. |
| M9 mapping | — | The reviewer mapped M9 to the deleted-issue tamper, but that tamper is still caught by the grant-id match. `test_a_duplicated_grant_issue_event` now isolates the transition rule, and M9 is caught by it. |

### Security

| # | Sev | Disposition |
|---|---|---|
| RS1 | Important | **Fixed (Andy approved option 2).** Unrecognised usage is charged the largest of U, `total_tokens`, and the chargeable counters present (`conservative_charge`), and R9 and AC9 are amended. The original finding: **Needs Andy's decision.** A paid call whose usage has an unrecognised shape is charged the sealed `unobserved_send_tokens`, exactly as the approved R9, P2 and F3 say. If a provider CLI changes its usage shape, every call would then be charged U, and real spend could run past the cap. Options: charge a conservative figure (the maximum of U, `total_tokens`, or the sum of the known counters present), or make `unrecognised_usage > 0` a hard gate condition. Either amends R9. For now the count is reported in `token_usage.unrecognised_usage` and trace. |
| RS2 | Suggestion | **Accepted residual.** Grants that are allowed but not yet consumed reserve no tokens. That is the concurrent-overshoot bound Andy chose, documented in ADR 0020 and R12. |
| RS3 | Suggestion | **Fixed.** Request-file reads use `O_NONBLOCK`, `fstat` S_ISREG and a size check. `read_request_file` validates the call id. The request directory must be a directory owned by the user with no group or world access. Tests: a FIFO at the final path, a traversal id, and a world-readable directory. |
| RS4 | Suggestion | **Fixed.** trace reads `run.json` through `process_identity.read_bounded`. |
| RS5 | Suggestion | **Fixed.** Every check is wrapped in a catch-all that records a failure. `_json` catches ValueError and RecursionError. The diff is decoded with `errors="replace"`. Directory listings are capped at 4,096 entries. Test: malformed sources fail their checks. |
| RS6 | Suggestion | **Fixed.** Work and attempt ids are validated in trace and verify-receipt, the charter digest is checked against a 64-hex pattern before any path join, and trace paths must be the two known trace names. Tests added. |
| RS7 | Suggestion | **Documented.** ADR 0020 marks request files as sensitive. `.flow/` is excluded from git (`.git/info/exclude`), and a run directory committed with `git add -f` carries them too. |

## Residual risks

- **RS1, resolved:** a usage block with no readable counter at all still charges U. It is reported as `unrecognised_usage`.
- **RS2 / R12:** the concurrent overshoot bound, accepted.
- **The fixture lineage uses stub supervisors.** One stock-runner lineage also verifies. Real providers are exercised by `v8-live-validation-4`, which is still to run.
- **QR17:** the lineage charge is computed twice per action decision.
