# ADR 0018: Manager progress repair and bounded retry

- Status: accepted
- Date: 2026-09-26
- Amends: the runner's strict progress parsing, and its `progress_ledger_retry_count=1`. ADR 0017's expansion semantics are unchanged.

## Context

The first chartered v8 attempt to get past its producer (`v8-live-validation-2`, attempt 1) sealed as `failed`. The Claude Magentic manager returned a progress ledger that was correct in substance, but one string contained an invalid JSON escape (a backslash before a backtick).

- The runner parsed progress replies with strict `json.loads` and aborted on failure.
- It had also set MAF's progress retry count to 1.
- So one malformed character ended an attempt whose paid edit had already completed.

MAF's own `_extract_json` rejects that reply too, so stock MAF would have retried rather than succeeded. Invalid escapes are a common failure mode for models writing JSON, and job text that is itself full of backslashes makes them more likely.

## Decision

A progress reply is repaired, or retried within a bound, and both cases are recorded. The checks that matter stay fail-closed.

- **One parser.**
  - `runtime/maf_runner/progress_parse.py` (standard library only) classifies a reply for both the runner and Flow (`cli/runner_progress.py` loads it by path).
  - Its candidate extraction copies MAF 1.2.0's `_extract_json`: the fenced block, else the first balanced object, plus its `True`/`False`/`None` variant.
  - MAF's last fallback, `ast.literal_eval`, is **deliberately omitted**, so a Python-literal reply is retried instead.
  - A parsed reply must also have the shape MAF's model needs: all five ledger items are objects with an `answer`.
- **Repair first.** If the candidate won't parse, the only repair is to escape each backslash that doesn't start a valid JSON escape:
  - `\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r` and `\t` are valid;
  - a backslash-u followed by 4 hex digits is valid;
  - anything else gets its backslash doubled.

  A reply that parses after this is **repaired**, with no extra call.
- **Canonical hand-off.**
  - The runner validates the object (speaker on the roster, completion decision, bounded task and rationale), then hands MAF `json.dumps(object)`.
  - The shared parser itself re-extracts the canonical text with its copy of MAF's rules. If that doesn't give back the same object, the reply is unparsable, for the runner and for Flow's evidence alike. This happens because MAF's fence rule applies even inside strings, and re-serializing can turn escaped backticks into a literal fence.
  - Where MAF can be imported, the runner also checks `_extract_json(canonical)` directly, as a parity guard.
  - Together these mean MAF always parses exactly what Flow validated. The progress reply never enters MAF's chat history, and Flow's recorded `output_sha256` stays the digest of the raw provider text.
- **Then a bounded retry.**
  - For an **unparsable** reply, the runner hands MAF a sentinel with no `{`. MAF's loop then retries, with `progress_ledger_retry_count=3`.
  - Each retry is a new Flow-gated manager call. MAF resends the same messages, so it has the same prompt digest, but the next sequence gives it a new call id.
  - A retry counts against `max_manager_calls`, including headroom, ADR 0017 expansion and the runner ceiling. It does **not** increment `manager_round`, because MAF's own round count doesn't move either.
- **Abort, don't replan.**
  - On the third consecutive unparsable reply, the runner raises `PolicyAbort("manager progress unparsable after 3 attempts")`.
  - `PolicyAbort` is a `BaseException`, so it gets past MAF's `except Exception` around `create_progress_ledger`. Without it, MAF would catch its own exhausted-retry error and start an unrequested replan (`_magentic.py:1088-1093`).
  - The attempt seals as `failed`.
- **Deterministic replay.**
  - Classification depends only on the recorded text. So `recover-delivery-lead` replay derives the same call ids, rounds and canonical texts, and sends nothing twice.
  - Restores start at a pending-action checkpoint, which only exists after a successful parse, so no retry is in flight at a restore point.
- **Evidence.**
  - A v8 receipt gains a `manager_progress` block, `{"repaired": [call ids], "unparsable": [call ids]}`. It is recomputed from the completed manager-call rows (request phase and response text), and is absent when both lists are empty.
  - The seal compares it with the ledger. `validate_receipt` recomputes it from the receipt's own manager calls, and rejects a tampered block, an empty block, or a block on a protocol version below 8.
  - A missing block is only caught at seal time, because receipts sealed before this ADR carry none. So a standalone `validate_receipt` of a post-ADR receipt with the block stripped passes. The seal comparison, and `sealed_receipt_sha256` for a sealed file, are what protect it.
  - The ledger also records `manager_progress_repaired` or `manager_progress_unparsable` in the observation's transaction. These events are diagnostic only.

## Consequences

- One malformed progress reply no longer fails an attempt. A retry costs one manager call, and may use headroom or pause for a decision.
- **Parser parity is pinned** to `agent_framework_orchestrations==1.2.0`. A MAF-gated test (`tests/test_progress_parse.py`) checks that MAF reads what Flow hands it exactly as Flow decided. It must pass on every MAF pin change.
- **Flow does change provider text in one bounded way:** doubling an invalid backslash, which is the only reading that makes the text JSON. The raw text stays the recorded observation.
- **D5 was found and fixed alongside this work.** Recovery that replayed a manager call granted from headroom had tried to regrant it. It now keeps that call's recorded answer (`delivery_gateway`, with a regression test in `tests/test_maf_expansion.py`).
