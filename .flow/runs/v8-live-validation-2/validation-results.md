# Validation Results: v8-live-validation-2

- **Date:** 2026-09-26 (UTC). Every recorded timestamp is from that day.
- **Installed CLI:** v0.36.2 for attempt 1, v0.37.0 for attempt 2. The sealed specialist digests were unchanged across both releases.
- **Worktree:** `~/src/flow-v8-live-job-2`, at job commit `d6d771f2`.
- **Charter:** v3 `dcba681b…`.
- **Outcome:** both attempts used, and no attempt completed. Classified as **validation found defects (R7)**.
  - **Fixed along the way:** D3, D4 and D5.
  - **Still open:** D6 (a misleading edit-check reason) and D7 (a design gap: the manager isn't told the producer gets exactly one turn).
  - The escalation chain was proven live for the first time.

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
- **Producer's reads:** 27 tool calls, none of them in `.flow` (`evidence/producer-tool-calls.txt`), so the result isn't contaminated by the first run's saved diff.

## Attempt 2: `0fa5602418374dfca3cfcf6f4c6c93d6` (v0.37.0)

- **Launch** (37 s): manager calls of 19.6, 8.6 and 8.5 s. Call 3 selected `docs-editor`, and the proposal was **denied into an expansion request** (`paid_worker_calls`: the lineage had used 1 of base 1, with 0 headroom). The attempt paused as `expansion_paused` with nothing sent.
- **Decision:** Andy said "Approved". I ran `decide-expansion --approve --expected-generation 1 --actor andy` (`evidence/decide-1.json`), which gave an engineer grant `expg-34a8…`. The decision wait was 759.6 s.
- **Recovery** (`recover-delivery-lead`, 21 s):
  - **pending mode:** the paused proposal was re-emitted under its original identity (a `duplicate_request` event);
  - the grant was consumed once, and the Claude edit was dispatched once. It **completed** in 20.2 s, with 1,705 output tokens.
- **Why it failed (D7, a Flow design gap).** The manager's delegation told the producer to **not edit any files yet**. The task ends "Report back the schema and rendering rules you find before making any edits … Do not edit any files yet." (see the receipt's `actions[0].request.task`).
  - The editor obeyed: 4 reads, 0 edits (`evidence/producer-tool-calls.txt`).
  - v8 allows one producer call per attempt and checks the edit straight after it, so the attempt sealed `failed`.
  - Flow never tells the manager about the one-turn rule. The facts Flow adds to the manager's task (`cli/delivery_gateway.py:1371-1381`) say Flow verifies the diff after the edit, but not that the producer gets one turn, which must make the complete edit.
  - The rationale Andy approved already said "must first inspect … before making any edits", so the decision gate could have warned about a single-turn grant for an inspect-only step.
  - **D6:** the reported reason, "editor changed files outside the approved job scope", is misleading. An empty change list falls into the scope branch at `cli/delivery_gateway.py:609-610`.
- **Receipt:** `validate_receipt` passes, and its hash matches the ledger. The `expansion` block lists the engineer grant (actor `andy`, consumed by the producer action), and `lineage_usage` counts attempt 1's paid call (`evidence/receipt-check-2.txt`).
- **Edit log:** 176 KB, with 0 `stream_event` records.

## Verdict per acceptance criterion

| AC | Verdict | Evidence |
|---|---|---|
| AC1 authority sealed | **Met** | v3 charter, limits and headroom (`inspect-preflight.json`, `delivery/*/delivery-charter.json`) |
| AC2 live preparation | **Met** | Both attempts prepared v8 envelopes with projected headroom, the roster `docs-editor` (Claude) and `local-verifier` (Ollama), and a Claude manager. The worktree was fresh and clean (preflight) |
| AC3 real providers | **Partly met** | Physical Claude turns for the manager and producer, with observed usage. There is **no in-attempt Ollama verifier evidence**, because the verifier was never reached; only the preflight gate exercised it. There was no `local_stub` |
| AC4 automatic grant | **Not reached** | Neither attempt got to manager call 5 |
| AC5 escalation observed and decided | **Met** (attempt 2) | Paused with nothing sent, `flow run status` showed the next action, and Andy decided it with `--expected-generation 1` |
| AC6 identical replay | **Partly met** | Worker-proposal replay was proven live: a `duplicate_request` event, a single `expansion_grant_consumed`, and one producer send (`receipt-check-2.txt`, `attempt-2-timings.txt`). **Manager-call replay wasn't reached live**; only the hermetic D5 regression test covers it |
| AC7 sealed valid receipt | **Met** | Both receipts validate and match the ledger. Attempt 2's includes the `expansion` block |
| AC8 verdict | **Not met: both attempts ended in Flow defects** | Attempt 1: D4. Attempt 2: D7 (a design gap), with D6 misreporting the reason |
| AC9 evidence | **Met with gaps** | **Present:** inspect snapshots at the pause and after the decision; the final inspect after both seals (`inspect-final*.json`, captured at review); receipts and their digests (`receipt-digests.txt`); ledger timings for every call; the verifier gate; the charter hash; the baseline; the first run's backfilled timings; Andy's words word for word. **Gaps:** `commands.txt` records the gated launch, decide, recover and cleanup commands, but not the preflight, inspect, status, timing and receipt-check commands. Those are recorded in their output files instead |
| AC10 attempt discipline | **Met** | Two attempts under the same sealed limits, with attempt 2 linked to attempt 1. Nothing was staged |
| AC11 documentation change | **Not applicable** | The job didn't complete |
| AC12 the D1 fix holds live | **Met** | Both edit turns completed, with 582,402 and 176,207 byte logs, 0 `stream_event` records and 1 terminal result each (`evidence/ac12-event-logs.txt`) |

## Deviations from the plan

- **Pauses between preflight and the attempts:** hours passed while three defects were fixed in their own runs (D3 in v0.36.2; D4 and D5 in v0.37.0). Preflight was re-run before each attempt.
- **Releases:** the authority was sealed on v0.36.1. Attempt 1 ran on v0.36.2 and attempt 2 on v0.37.0. The sealed specialist digests were re-checked and unchanged each time, and runner code isn't part of the sealed sources.
- **Worktree reset:** the job worktree was reset between the attempts, restoring the 4 files after checking that the diff matched the saved `evidence/attempt-1-worktree.diff` byte for byte (`preflight.txt`).
- **AC10 narrowing:** AC10's "retuned limits" was narrowed to the same sealed limits (plan amendment, plan-review F7).
- **Re-warm before recovery:** before `recover-delivery-lead` (plan step 9), the model was re-warmed with `keep_alive: -1` and `ollama ps` showed `Forever`. That was seen in the session, but not saved to an evidence file. Attempt 2's preflight `ollama ps` also wasn't saved; the gate's 3.1 s warm result was.
- **Plan step 16:** the tag SHA in the plan was mistyped (43 characters). The correct 40-character `c864241ab064…` was resolved from the old worktree's HEAD, and the first try failed safely, before anything was removed (`commands.txt`).
- **`receipt-check-1.txt` shows `headroom: None`:** the check script read the wrong envelope key. The envelope's top-level `expansion_headroom` is `{delegations 1, manager_calls 1, verifier_calls 1}`, so AC2's projected headroom holds.

- **Mutation check:** not applicable. This run changed no Flow code; the fixes were in their own runs.
- **Validated against:** real providers. There is no surrogate.
