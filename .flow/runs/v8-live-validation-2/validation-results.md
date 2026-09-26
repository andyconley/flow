# Validation Results: v8-live-validation-2

- **Dates:** 2026-09-26 and 2026-09-27 (UTC).
- **Installed CLI:** v0.36.2 for attempt 1, v0.37.0 for attempt 2. The sealed specialist digests were unchanged across both releases.
- **Worktree:** `~/src/flow-v8-live-job-2`, at job commit `d6d771f2`.
- **Charter:** v3 `dcba681b…`.
- **Outcome:** both attempts used, and no attempt completed. Classified as **validation found defects (R7)**. Four Flow defects were found and fixed along the way (D3, D4, D5, D6), and D6 is still open. The escalation chain was proven live for the first time.

## Before any paid call

- **D3, found by the preflight verifier gate.** `gemma4:26b`'s reasoning used the whole 1,024-token verifier output budget on a real diff, so the answer came back empty.
  - Fixed in `ollama-verifier-think` (v0.36.2): `think: false`.
  - The gate then passed: 4.9 s, then 3.1 s.
  - Evidence: `evidence/d3-verifier-thinking.txt`, `verifier-gate*.json`.

## Attempt 1: `22ab86c3559e4fd89e47cb9e59ebece2` (v0.36.2, 158 s)

- **Calls:** manager calls of 31.4, 8.1 and 12.3 s. Then the Claude edit took 89.5 s, **completed**, and the targeted test passed. Then manager call 4 took 15.4 s. (`evidence/attempt-1-timings.txt`)
- **D1 held live:** a 582 KB event log, 0 `stream_event` records, and 1 terminal result (AC12).
- **Sealed `failed`.** The reason was "manager progress is not valid JSON", which is **D4**: one invalid JSON escape in an otherwise correct reply, with no retry.
  - Fixed in `manager-progress-retry` (v0.37.0, ADR 0018).
  - While testing that fix, **D5** was found: recovery failed after any charter-headroom grant. It sits exactly on this run's planned resume path, and was fixed in the same release.
- **Receipt:** valid, and its hash matches the ledger (`evidence/receipt-check-1.txt`).
- **Producer's reads:** 27 tool calls, none of them in `.flow`, so the result isn't contaminated by the first run's saved diff.

## Attempt 2: `0fa5602418374dfca3cfcf6f4c6c93d6` (v0.37.0)

- **Launch** (37 s): manager calls of 19.6, 8.6 and 8.5 s. Call 3 selected `docs-editor`, and the proposal was **denied into an expansion request** (`paid_worker_calls`: the lineage had used 1 of base 1, with 0 headroom). The attempt paused as `expansion_paused` with nothing sent.
- **Decision:** Andy said "Approved". I ran `decide-expansion --approve --expected-generation 1 --actor andy` (`evidence/decide-1.json`), which gave an engineer grant `expg-34a8…`. The decision wait was 759.6 s.
- **Recovery** (`recover-delivery-lead`, 21 s):
  - **pending mode:** the paused proposal was re-emitted under its original identity (a `duplicate_request` event);
  - the grant was consumed once, and the Claude edit was dispatched once. It **completed** in 20.2 s, with 1,705 output tokens.
- **Why it failed:** the manager's instruction was inspect-only ("inspect the schema/format … before making any edits"). The editor read 4 files and returned a summary, with **no edits**. v8 allows one producer call per attempt and checks the edit straight after it, so the attempt sealed `failed`.
  - **D6:** the reported reason, "editor changed files outside the approved job scope", is misleading. An empty change list falls into the scope branch at `cli/delivery_gateway.py:609-610`.
- **Receipt:** `validate_receipt` passes, and its hash matches the ledger. The `expansion` block lists the engineer grant (actor `andy`, consumed by the producer action), and `lineage_usage` counts attempt 1's paid call (`evidence/receipt-check-2.txt`).
- **Edit log:** 176 KB, with 0 `stream_event` records.

## Verdict per acceptance criterion

| AC | Verdict | Evidence |
|---|---|---|
| AC1 authority sealed | **Met** | v3 charter, limits and headroom (`inspect-preflight.json`, `delivery/*/delivery-charter.json`) |
| AC2 live preparation | **Met** | Both attempts prepared v8 envelopes with projected headroom, the roster `docs-editor` (Claude) and `local-verifier` (Ollama), and a Claude manager. The worktree was fresh and clean (preflight) |
| AC3 real providers | **Met for manager and producer** | Physical Claude turns with observed usage. The verifier was never reached in either attempt; there was no `local_stub` |
| AC4 automatic grant | **Not reached** | Neither attempt got to manager call 5 |
| AC5 escalation observed and decided | **Met** (attempt 2) | Paused with nothing sent, `flow run status` showed the next action, and Andy decided it with `--expected-generation 1` |
| AC6 identical replay | **Met for the worker proposal** | The same proposal was replayed, the grant consumed once, and the producer sent once. Manager-call replay wasn't reached live; the D5 regression test covers it hermetically |
| AC7 sealed valid receipt | **Met** | Both receipts validate and match the ledger. Attempt 2's includes the `expansion` block |
| AC8 verdict | **Recorded** | Attempt 1: Flow defect (D4). Attempt 2: failed, because the manager's inspect-only delegation conflicts with the one-producer-call contract, plus D6 |
| AC9 evidence | **Met** | Commands word for word (`evidence/commands.txt`, including Andy's words), inspect snapshots, receipts, ledger timings, the verifier gate, the charter hash, the baseline, and the first run's backfilled timings |
| AC10 attempt discipline | **Met** | Two attempts under the same sealed limits, with attempt 2 linked to attempt 1. Nothing was staged |
| AC11 documentation change | **Not applicable** | The job didn't complete |
| AC12 the D1 fix holds live | **Met** | Both edit turns completed, with 582 KB and 176 KB logs and 0 partial records |

- **Mutation check:** not applicable. This run changed no Flow code; the fixes were in their own runs.
- **Validated against:** real providers. There is no surrogate.
