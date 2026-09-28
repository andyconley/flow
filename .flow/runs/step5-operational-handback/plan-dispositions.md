# Plan Dispositions: step5-operational-handback

- **Source:** `plan-review.md` (architect, read-only; advisory expertise `no_match`, request `89c28aa3-e1c6-4415-a08b-09a94ce5dc4d`).
- **Amendments:** each accepted finding becomes an amendment, A1–A18, in `plan.md` § "Amendments from plan review". An amendment overrides the design text it touches.
- **The R10/AC10 amendment reached the reviewer mid-review.** Its I2-dependent items (PR10 on I2, and PR17 M11) are re-based on the amended text.

| # | Sev | Disposition |
|---|---|---|
| PR1 | Critical | **Accepted (A1).** `_seal_blocks_locked` never raises. The legacy lineage key set is chosen by `handback_supported`. The default includes `predecessor_charged: 0` for supported attempts only. The "refuse to advance" rule moves to the gate, `_seal_attempt` and `finish_attempt`. New C3 tests abandon a legacy started attempt, with and without a legacy predecessor. |
| PR2 | Important | **Accepted (A2).** The V15 fold validates every transition. New mutation M9. |
| PR3 | Important | **Accepted (A3).** Escalation windows exist only for requests not granted by `charter_headroom`. A window still open at seal fails V15. |
| PR4 | Important | **Accepted, option (a) (A4).** The three record-time validators check only the known keys and ignore extras, as the approved R9 and AC9 say. New AC9 cases cover a nested extra key (Codex) and a string extra key (manager). Negative or non-integer *known* keys stay rejected. |
| PR5 | Important | **Accepted (A5).** fsync the directory after the link and on reuse. `.*.tmp` files are informational in V10. New AC2 case: a kill after the temp file is created. |
| PR6 | Important | **Accepted (A6).** `previous_checkpoint_id` is projected for protocol 8 only. |
| PR7 | Important | **Accepted (A7).** `project_envelope_limits` goes in `delivery_contracts.py`, shared by prepare and V7, with an identity assertion. The claim walk indexes claims by recomputed digest. |
| PR8 | Important | **Accepted (A8).** The AC3 enumeration is hardened: all three `execute` variants, case-insensitive matching including DELETE and REPLACE, a multiset of sites, and non-static SQL fails unless allowlisted. |
| PR9 | Suggestion | **Accepted (A9).** `:1958` is reclassified as "not a grant change". `:1960` stays v8-unreachable. The results note that R3's `resolved_not_dispatched` path emits nothing in v8. |
| PR10 | Suggestion | **Accepted (A10).** The D2 absolute ceiling and I3 are flagged to Andy at plan approval. Lapsed engineer tranches are conservatively counted as outstanding, and ADR 0020 records this. The I2 part is superseded by the R10/AC10 amendment. |
| PR11 | Suggestion | **Accepted (A11).** AC22 fixture deviations are named per category in `validation-results.md`. |
| PR12 | Suggestion | **Accepted (A12).** V13 passes on cancelled and abandoned attempts (the baseline is always written). Only V11 and V12 are `not_applicable` there. `validation-plan.md` records this. |
| PR13 | Suggestion | **Accepted (A13).** verify uses only `process_identity.records()`. The handoff's trace wording allows a non-blocking liveness probe but no created lock file. The subprocess and socket patch applies to verify. |
| PR14 | Suggestion | **Accepted (A14).** The v5 next-command at `:2453` gains `--actor`. The `on_process_group is None` guard is added. |
| PR15 | Suggestion | **Accepted (A15).** The request file is written before `stop_if_cancelled()`. The V10 requiredness rule is stated. |
| PR16 | Suggestion | **Accepted (A16).** `tests/manager_stub.py` lands in C1. `predecessor_charged` lands in C3 only. A legacy-row SQL helper is named. The C2 `lineage_view` returns the pre-C3 blocks. |
| PR17 | Suggestion | **Accepted, re-based (A17).** New mutations M9, M10, M12 and M13. M11 becomes "reintroduce a hard token_cap refusal at 0 headroom". It must fail the amended AC10. |
| PR18 | Suggestion | **Accepted (A18).** Added: a Codex manager identity case; enumerated trace outputs and golden normalisation; the AC12c overshoot assertion via `seal_view`. An `envelope.json` file that is supported while the ledger envelope is legacy fails V2 (exit 1). Codex `cache_write_input_tokens` appears only in trace's raw usage. |

## Plan approval (2026-09-27)

Andy approved the plan with A1–A18. He also confirmed:
- **D2:** the absolute tranche ceiling applies to engineer grants too.
- **I3:** a single answer-mode recovery covers both the escalation resume and the D5 replay.
