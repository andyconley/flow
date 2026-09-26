# Validation Results: manager-progress-retry

- **Date:** 2026-09-26.
- **Branch:** `codex/manager-progress-retry`, from `main` at v0.36.2 (`e0046ef`).
- **Commits:** 5c3a4f1, 0dddf5f, 0ff2387 (D5), 40249cb, 454b34d, b377351 (review fixes), 81531e0.

## Verdict per acceptance criterion

| AC | Verdict | Evidence |
|---|---|---|
| AC1 real-data regression | **Met** | `test_progress_parse::test_recorded_live_reply_is_repaired_and_selects_the_verifier`: the verbatim fixture from `v8-live-validation-2` attempt 1 is repaired and selects `local-verifier`, and the raw text still fails `json.loads`. The MAF parity test confirms MAF reads the canonical text as the same object. `test_maf_progress_retry::RepairedReplyTests` covers it end to end |
| AC2 repair is exact | **Met** | The escape cases include `\u12`, `\uZZZZ`, an escaped backslash followed by a backtick, valid replies never marked repaired, and a broken reply whose valid `\\`, `\"` and `\t` pairs survive |
| AC3 bounded retry | **Met** | In the runner: 1 retry is 1 extra call in the same round, and 3 unparsable replies give an error with no replan and no worker. A missing ledger item is retried like an unparsable reply, and a missing speaker reason gives `PolicyAbort` with no replan. At the gateway: `ExhaustedRetriesTests` seals `failed` with the reason |
| AC4 accounting | **Met** (with residual risk) | `RetryPastBaseIsGrantedFromHeadroomTests`: the retry is the 7th call, granted automatically from headroom. Denial at the runner ceiling for a retry specifically isn't tested; that path is generic ADR 0017 behaviour (T5) |
| AC5 parity | **Met** | `ProgressParseMafParityTests` (MAF-gated) runs 17 corpus cases through MAF's real `_extract_json` and `_coerce_model`, on exactly the text Flow hands MAF |
| AC6 replay identity | **Met** | `ReplayThroughRetryTests`: pause, approve, recover, with identical call ids, no manager call sent twice, and completed actions answered rather than resent |
| AC7 audit | **Met** | The block is present with the right ids for a retry and for a repair, and absent for a clean run. `validate_receipt` rejects tampered, empty and null blocks, and a block on protocol 7 (checked directly). The event is written in the observation's transaction (`test_progress_diagnostic_event_commits_with_the_observation`) |
| AC8 no regressions | **Met** | Full suite: **1,562 tests OK, 0 skipped**, with `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python`. The first run caught one real failure: the release-staging sibling list needed `runner_progress`, and it has been added |
| AC9 documentation | **Met** | `docs/adr/0018-manager-progress-repair-and-retry.md`, and `docs/maf-adoption-design.md:24` |

## D5 (found during implementation, engineer approved including it)

- **The defect:** recovery replayed a manager call that had been granted from headroom, and tried to regrant it, so the attempt sealed `failed` with `expansion_grant_consumed`.
- **Reproduced on unchanged `main`** with the live run's own limits (base 4 plus 1 headroom: call 5 granted automatically, call 6 escalates). This was the exact path `v8-live-validation-2` planned to exercise.
- **Fix:** `delivery_gateway` regrants only a replayed call with no recorded result.
- **Regression test:** `tests/test_maf_expansion.py::AutomaticGrantThenEscalationReplayTests`.

## Mutation checks: 10 of 10 caught

| # | Mutation | Caught by |
|---|---|---|
| M1 | remove the escape repair | `test_progress_parse` (4 failures) |
| M2 | retry count back to 1 | `test_maf_delivery_lead` (3) |
| M3 | return the sentinel instead of aborting on the 3rd | `test_maf_delivery_lead` (1, no-replan test) |
| M4 | drop the shape check | `test_progress_parse` (4) and `test_maf_delivery_lead` (1) |
| M5 | increment the round on a retry | `test_maf_delivery_lead` (2) |
| M6 | drop the receipt block recomputation | `test_maf_progress_retry` (3) |
| M7 | treat `\\` as invalid in the scan | `test_progress_parse` (1). It survived at first, and was caught after the mixed-repair test was added |
| M8 | remove the D5 guard | `test_maf_expansion` (1) |
| M9 | remove the round-trip check | `test_progress_parse` (2) |
| M10 | remove the protocol-v8 guard | `test_maf_progress_retry` (1) |

- **Validated against:** the change itself, with hermetic and MAF-gated tests on the pinned MAF (core 1.19.0, orchestrations 1.2.0). There were no live provider calls. The live proof is `v8-live-validation-2` attempt 2, after release.
- **Reviews:** architect (plan, A1–A7), quality and test (implementation). All dispositions are in `adversarial-review.md` and `implementation-review.md`.
