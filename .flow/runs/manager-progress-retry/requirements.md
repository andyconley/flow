# Requirements: manager progress repair and bounded retry

- **Status:** revised after the architect's review (`adversarial-review.md`, A1–A7 all accepted), pending engineer approval. Drafted 2026-09-26 from engineer decisions in `flow-plan` (all five recommendations accepted).
- **Why definition:** `start-plan` requires an approved definition, so this bug-shaped work carries a compact definition. (Gap: `plan-entry-without-definition`.)

## Problem

In `v8-live-validation-2`, attempt 1 (`22ab86c3…`) sealed as `failed`, with the reason "MAF delivery child failed: manager progress is not valid JSON".
- The Claude manager's fourth call returned a progress ledger that was correct in substance: it selected `local-verifier` next.
- But one string contained an invalid JSON escape: a backslash before a backtick.
- The runner's `_validate_progress` (`runtime/maf_runner/delivery_lead.py:71-76`) parses with strict `json.loads` and aborts the attempt with `PolicyAbort`.
- The runner also sets `progress_ledger_retry_count=1` (`delivery_lead.py:259`), which disables MAF's own retry loop (stock default: 3 attempts).

So one malformed character in a provider reply ends a whole chartered attempt, after a paid edit had already completed. MAF's own parser (`_extract_json`) also rejects that reply, so stock MAF would have retried rather than succeeded.

- **Evidence:** `.flow/runs/v8-live-validation-2/evidence/` (launch-1.json, attempt-1-timings.txt, receipt-check-1.txt) and the manager call's text, which is stored in that run's ledger.

## Audience

Andy, who runs v8 chartered jobs. This fix blocks attempt 2 of `v8-live-validation-2`.

## Desired outcome

A malformed manager progress reply is recovered in a bounded, auditable way. The checks that matter stay fail-closed:
- the speaker must be on the roster;
- the task and rationale must be bounded;
- manager-call limits and expansion still apply;
- replay identity is preserved.

## Requirements (engineer decisions 1a–5a, 2026-09-26)

- **R1, repair first.** For a progress-phase reply, Flow extracts the JSON object using the same candidate rules as MAF's `_extract_json` (R3).
  - If `json.loads` fails, Flow applies one deterministic repair: every backslash followed by a character that isn't a valid JSON escape (anything other than `"` `\` `/` `b` `f` `n` `r` `t` `u`) becomes an escaped backslash (`\\`). Valid escapes are untouched.
  - If the repaired candidate parses to an object, the reply counts as **repaired**.
  - No other repair is attempted.
- **R2, then bounded retry.** If the reply still doesn't yield an object, it is **unparsable**. Flow then lets the stock manager retry the progress step.
  - The runner sets `progress_ledger_retry_count=3`, which means at most 2 retries per progress step.
  - Each retry is a new Flow-gated manager call with its own call identity, since the sequence advances. It counts against `max_manager_calls`, including charter headroom and expansion, and against the runner ceiling.
  - A retry does **not** increment `manager_round`.
  - If all 3 attempts are unparsable, the runner's manager proxy raises `PolicyAbort("manager progress unparsable after 3 attempts")` on the third reply, and the attempt seals as `failed` (A1).
    - `PolicyAbort` is a `BaseException`, so it gets past MAF's `except Exception` around `create_progress_ledger`.
    - Otherwise MAF would swallow its own exhausted-retry error and start an unrequested replan (`_magentic.py:1088-1093`).
    - The consecutive-unparsable counter and `retry_pending` reset on every successful parse.
- **R3, parser parity.** Flow's extraction follows MAF's `_extract_json` candidate rules: fenced JSON, else the first balanced object, plus the `True`/`False`/`None` variant.
  - Flow decides validity, and hands MAF a canonical re-serialization (`json.dumps` of the validated object), so MAF's parse always equals Flow's object.
  - For an unparsable reply, Flow hands MAF text that MAF's parser is certain to reject, which triggers MAF's retry.
  - The roster, satisfaction, task and rationale checks run on the extracted object.
  - **A parsed reply must also have the shape MAF expects (A3).** All five ledger items (`is_request_satisfied`, `is_in_loop`, `is_progress_being_made`, `next_speaker`, `instruction_or_question`) must be objects with an `answer`. Otherwise the reply counts as unparsable, the same in the runner and the gateway, because MAF's `_coerce_model` would otherwise throw and retry behind Flow's back.
  - **Round-trip check (A5).** Where MAF can be imported (the runner), Flow checks `_extract_json(canonical) == value`. A mismatch counts as unparsable.
  - **`ast.literal_eval` is left out on purpose (A6).** Python-literal replies go to retry. Parity is measured on the text Flow hands MAF.
- **R4, deterministic replay.** Repair and retry decisions depend only on the recorded provider text. So `recover-delivery-lead` replay derives identical call ids, rounds and canonical texts. It sends no duplicate.
- **R5, audit trail.**
  - **Receipt block (A2).** The receipt carries a `manager_progress` block, with `repaired` and `unparsable` call-id lists.
    - It is computed at seal time from the ledger's completed `manager_calls` rows: the phase comes from `request.phase` and the text from `result.output`. Receipts already carry both, so there is no separate event to lose in a crash.
    - The block is absent when both lists are empty. An empty block is invalid.
  - **Validation (A7).** `validate_receipt` recomputes the block over completed progress calls and rejects it on a mismatch, or on protocol versions below 8.
  - **Ledger events.** The ledger also records `manager_progress_repaired` or `manager_progress_unparsable` for diagnostics. They are written inside `observe_manager_response`, in the same transaction, with the phase passed in. They are secondary to the receipt block.
- **R6, scope.** Only the progress phase is affected. Facts, plan, replan and final replies aren't parsed as JSON and don't change.
- **R7, record the decision.** A new ADR (0018) records the repair-then-retry decision and its accounting.

## Non-goals

- Tolerant parsing of anything beyond the one escape repair and MAF's candidate rules.
- Changing the prompts.
- Retries for non-progress phases or for provider transport errors.
- Changing the specialist definitions (the sealed digests stay valid).
- A new execution protocol version (v8 receipts gain an optional block, as `expansion` did).

## Constraints

- The runner uses only the standard library, plus MAF at pinned versions (core 1.19.0, orchestrations 1.2.0).
- The parser module lives in `runtime/maf_runner/` and is loaded by path from `cli/`, as `runner_limits.py` is.
- ADR 0016 lock order, generation fencing and ADR 0017 expansion semantics still hold.

## Assumptions

- **A1.** MAF's retry loop resends the same messages, so a retried call has the same prompt digest with a higher sequence. To be confirmed in the MAF-gated tests.
- **A2.** An unparsable reply that MAF's `_extract_json` would accept (through its `ast.literal_eval` fallback) is impossible, because Flow never passes raw text through. To be confirmed by the parity tests.
