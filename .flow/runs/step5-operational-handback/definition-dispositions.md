# Definition Dispositions: step5-operational-handback (revision 1 → 2)

Sources:
- `adversarial-review.md`: architecture, F1–F21;
- `adversarial-product.md`: product, P-F1–P-F9.

## Architecture

| # | Sev | Disposition |
|---|---|---|
| F1 | Critical | **Accepted.** `tokens` counts tranches, with base 0 and ceiling `MAX_TOKEN_TRANCHES`. Only the token predicate converts tranches to tokens. A shortfall needing more than one tranche is a hard stop (P3a). The charter rule `token_tranche ≥ unobserved_send_tokens` is added. The touch points are named in R8. New AC: AC12b. |
| F2 | Critical | **Accepted.** Charging goes by row status only (P2), through a pure per-row function that the gate, the seals, the validator, trace and verify-receipt all share (R9). `response_observations` and the resolution source are dropped. |
| F3 | Important | **Accepted.** Normalisation is tolerant. An unrecognised shape is charged the sealed amount and reported as `unrecognised_usage`; it is never refused at record time (R9, AC9). |
| F4 | Important | **Accepted.** V7 checks against the sealed claim files and the `supersedes` chain. `run.json` is used only to find the current claim. |
| F5 | Important | **Accepted in part.** The finding's analysis is accepted, and R12 now states the concurrent bound: up to `max_concurrent` paid actions plus one paid manager call. Andy chose to keep concurrency (2026-09-27), so serialisation is **not** added. New AC: AC12c. |
| F6 | Important | **Accepted.** R10 gives each path its own rule: expansion only on the initial decide, and a hard denial on the regrant and reissue paths. `reissue_recovered_manager_grant` gets the full checks, excludes its own row, and fails the attempt when denied. The checks are shared in `_v8_manager_checks`. |
| F7 | Important | **Accepted.** Whether a receipt is supported is decided from the ledger envelope's contract version (P9). A supported receipt with a missing block fails (AC17). |
| F8 | Important | **Accepted.** R5 is informational. V9 checks bound links only. An unbroken-chain rule is a non-goal. |
| F9 | Important | **Accepted.** The tautology is replaced by seq-precedence checks. Escalation windows are defined by seq. The send-start event is defined per row kind. The grant end state covers release and expiry (V15). |
| F10 | Important | **Accepted.** AC16 now declares exact expected failure sets, including a tamper of receipt bytes only. |
| F11 | Important | **Accepted.** The request file is written before consume, under `send_lock`, and linked into place atomically. Its content is canonical and has no timestamps. `render_manager_prompt` binds Claude's `input_sha256`. V10 accepts allowed-but-unsent calls and flags orphan files (R2, AC2). |
| F12 | Important | **Accepted.** A new `grant_changed` event is added, and the existing details are untouched. AC3 is structural and covers the full path list (R3). |
| F13 | Important | **Accepted.** The snapshot is taken under the sealing `send_lock`, after `close_expansions`. Keys are compared exactly (R16, AC20). |
| F14 | Important | **Accepted.** The requiredness table per status is in R14. V11 is pinned to the final verifier input. |
| F15 | Suggestion | **Accepted** as V17, the token gate replay. |
| F16 | Suggestion | **Accepted.** The file mode is an informational item outside the exit code. |
| F17 | Suggestion | **Accepted.** A reverse check is added, and V16 is labelled a consistency check. |
| F18 | Suggestion | **Accepted.** `predecessor_charged` lives in `lineage_usage`. A superseded predecessor is handled. Predecessors are cross-checked in V6. |
| F19 | Suggestion | **Accepted** as blocking planning questions, each backed by a captured fixture. ADR 0020 says the unit is not a cost proxy. |
| F20 | Important | **Closed.** The coordinator read `receipt_check.py` and the live receipt from branch `codex/v8-live-validation-3`. `reconciliation.md` maps each check. |
| F21 | Suggestion | **Accepted.** The commit order is in Constraints. verify-receipt reads in one transaction and takes no lock. trace is v8-only. The callers of `recover_delivery` are covered (R6). The candidate cuts are held back: no cut is needed yet. The plan may propose one. |

## Product

| # | Sev | Disposition |
|---|---|---|
| P-F1 | Important | **Kept R2** (Andy, 2026-09-27). After F11 it is a small, bounded change, and it gives V10 and the Claude identity binding. The PR size is managed by the commit order. |
| P-F2 | Important | **Accepted** as P10. The defaults and ceilings are derived from the `v8-live-validation-3` receipt (133,898 charged tokens in the lineage; largest call 82,376). The derivation is recorded in ADR 0020. |
| P-F3 | Suggestion | **Accepted.** Token counts are absolute in trace, in the pending detail and in refusals (R7). |
| P-F4 | Suggestion | **Accepted** as P10: `unobserved_send_tokens` is 100,000, about 1.2 × the largest observed call. |
| P-F5 | Important | **Accepted.** Failure details are diagnostic (R13, AC16). |
| P-F6 | Important | **Accepted.** trace leads with a status banner, golden-pinned (R7, AC7). |
| P-F7 | Important | **Accepted as non-goals.** The job-charter digest and symlink hygiene are named, each with a reason. The success criterion's claim is narrowed to match the reconciliation mapping. |
| P-F8 | Suggestion | **Resolved by F11.** `call_id` is derived from `prompt_digest`, so different messages give a different call and a different file. For the same call, differing bytes can only come from corruption, and they refuse. |
| P-F9 | Suggestion | **Accepted.** The `--json \| jq` note goes in the CLI reference. There is no filter flag. |
