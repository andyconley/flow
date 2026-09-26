# Plan: manager progress repair and bounded retry

- **Status:** revised after the architect's review (`adversarial-review.md`, A1 blocking, A2–A3 major, A4–A7 minor, all accepted), pending engineer approval.
- **Inputs:** `requirements.md` (R1–R7) and `acceptance-criteria.md` (AC1–AC9).
- **Branch:** `codex/manager-progress-retry`, from `main` at v0.36.2.

## Change map (file level)

1. **New `runtime/maf_runner/progress_parse.py`** (standard library only), holding the single parser that both the runner and Flow use.
   - `extract_candidate(text) -> str`: a copy of MAF 1.2.0 `_extract_json`'s candidate rules. That's the fenced ```` ```json ```` block, else the first balanced `{…}`. It raises `ValueError` when there is none. A comment pins it to `agent_framework_orchestrations==1.2.0`.
   - `repair_escapes(candidate) -> str`: a single left-to-right scan.
     - It keeps each valid escape pair intact: a backslash followed by one of `\"\\/bfnrt`, or `\u` followed by 4 hex digits (A4).
     - It doubles a backslash before any other character.
     - The scan consumes `\\` as one pair, so an already-escaped backslash is never re-escaped.
   - `parse_progress(text) -> ProgressParse`, with the fields `value` (a dict or None), `repaired` (bool) and `canonical` (the `json.dumps(value, ensure_ascii=False, sort_keys=False)` text, or None). It works as follows:
     - extract the candidate;
     - try `json.loads` on the candidate, then on its `True`/`False`/`None` variant (MAF's second attempt);
     - otherwise repair and retry both variants;
     - a result must be a dict whose five ledger items (`is_request_satisfied`, `is_in_loop`, `is_progress_being_made`, `next_speaker`, `instruction_or_question`) are all dicts containing `answer` (A3). Anything else is unparsable.
     - Python literals (`ast.literal_eval`) are deliberately not accepted (A6).
   - `UNPARSABLE_SENTINEL`: a constant with no `{`, which `_extract_json` is certain to reject. For example: `"flow: progress reply was not valid JSON"`.
2. **`runtime/maf_runner/delivery_lead.py`:**
   - `_validate_progress(value, roster)` now takes the parsed dict, and keeps every current check: speaker on the roster, satisfaction and completion rules, task and rationale bounds.
   - In `ManagerProxy.run`, for the progress phase:
     - **Rounds:** the existing `manager_round += 1` (for progress calls after call 3) is skipped when the previous progress call was unparsable. A `retry_pending` flag tracks this; it is set on unparsable and cleared on success.
     - **Parsing:** after `reply = _read()`, call `parse_progress(response_text)`.
     - **Parsed** (`value` is not None): validate it, set `selected_task` and `selected_reason` from it, and return an `AgentResponse` with `parsed.canonical`.
     - **Round-trip check (A5):** when MAF is importable, also require `_extract_json(parsed.canonical) == parsed.value`. On a mismatch, treat the reply as unparsable.
     - **Unparsable:** increment `unparsable_streak`.
       - On the 3rd consecutive one, raise `PolicyAbort("manager progress unparsable after 3 attempts")` (A1).
       - Otherwise set `retry_pending` and return an `AgentResponse` with `UNPARSABLE_SENTINEL`, and MAF's loop retries.
       - Success clears both `unparsable_streak` and `retry_pending`.
   - `StandardMagenticManager(..., progress_ledger_retry_count=3)`.
   - **MAF's own give-up must never run (A1).** `_magentic.py:1088-1093` catches the exhausted-retry `RuntimeError` and replans. `PolicyAbort` is a `BaseException` (`delivery_lead.py:25`), so it gets past that handler. It then surfaces as the child's `error` message (`delivery_lead.py:359-361`), then the gateway's `failure` (`:1615`), and the attempt ends terminal `failed` (`:1270`). A test asserts that no replan call follows.
   - **Replay:** during `recover-delivery-lead`, recorded texts are replayed, and the same `parse_progress` gives the same results. So `retry_pending` and `manager_round` evolve the same way, and call ids match (R4, AC6).
     - Resume always starts from a pending-action checkpoint, which only exists after a successful parse. So assert that `retry_pending` and `unparsable_streak` are zero at resume, with a comment explaining why.
3. **New `cli/runner_progress.py`:** a path loader for `runtime/maf_runner/progress_parse.py`, mirroring `cli/runner_limits.py`, with type checks on what it loads.
4. **`cli/delivery_gateway.py`, on manager response observation** (around `:1406-1456`): pass the request's phase to `observe_manager_response`. For a `progress` phase, the ledger classifies the text with `parse_progress` and writes `manager_progress_repaired` or `manager_progress_unparsable` **in the same transaction** as the observation (A2). The shape check (A3) applies here too.
5. **`cli/execution_ledger.py`:**
   - `observe_manager_response` gains an optional `phase` and writes the diagnostic event inside its transaction;
   - **the seal builds the receipt's `manager_progress` block from the completed `manager_calls` rows** (A2): the phase from `request.phase`, the text from `result.output`, and `{"repaired": [call_ids], "unparsable": [call_ids]}`. It omits the block when both lists are empty;
   - the seal comparison includes the block.
6. **`cli/execution_contracts.py`:** `_validate_magentic_receipt` accepts the optional `manager_progress` block for v8 only (A7).
   - Receipts carry each completed call's `result.output` (`execution_ledger.py:2530`, required at `execution_contracts.py:1014`). So the validator re-runs `parse_progress` over completed progress-phase calls, and requires the block to equal the recomputation.
   - It rejects a tampered block, an empty block, and any block on a protocol version below 8.
7. **Tests:**
   - **New `tests/test_progress_parse.py`** (not MAF-gated):
     - AC2's escape cases, including `\\` followed by a backtick;
     - the AC1 fixture, a verbatim copy of the failing reply at `tests/fixtures/manager_progress_invalid_escape.txt`, taken from the run ledger;
     - `\u12`, `\uZZZZ`, and an escaped backslash followed by a backtick (A4);
     - fenced, wrapped, Python-literal and garbage replies, plus an instruction containing a fenced object (A5);
     - the sentinel check.
   - **The same file, MAF-gated:** parity with `agent_framework_orchestrations._magentic._extract_json` on the corpus (AC5). For every case, MAF parsing Flow's output (canonical or sentinel) agrees with Flow's decision.
   - **MAF end-to-end cases**, in `tests/test_maf_expansion.py` or a new `tests/test_maf_progress_retry.py` using the existing fake-manager fixtures:
     - a repaired reply leads to no extra call, the attempt continues, and the event is recorded;
     - one unparsable reply then a valid one leads to +1 call and the same rounds;
     - three unparsable replies fail the attempt with the reason, and **no replan call follows** (A1);
     - a reply with valid JSON but a missing or non-object ledger item counts as unparsable (A3);
     - a retry that pushes past the base manager calls is granted automatically from headroom (AC4);
     - pause and recover after a retry replays identically (AC6).
   - **Receipt tests:** the block is present or absent as appropriate, and a tampered block is rejected.
8. **Docs:** a new `docs/adr/0018-manager-progress-repair-and-retry.md`. It records why the runner aborts on the 3rd unparsable reply rather than letting MAF replan (A1), that the receipt block is recomputed from rows (A2), and that `literal_eval` is deliberately left out (A6). `docs/maf-adoption-design.md` gets a short reference to it.

## Commits (Conventional Commits)

1. `feat(runtime): add shared manager progress parser`, with its unit tests.
2. `fix(runtime): repair or retry malformed manager progress`, the runner change plus the MAF end-to-end tests.
3. `feat(cli): record manager progress repairs in the ledger and receipt`, the gateway, ledger and contracts changes plus the receipt tests.
4. `docs(adr): record manager progress repair and bounded retry`.

## Validation

- Every AC in `validation-plan.md`.
- **Mutation checks:**
  - remove the repair, and AC1 fails;
  - retry count back to 1, and AC3 fails;
  - return the sentinel on the 3rd unparsable reply instead of aborting, and the no-replan test fails (A1);
  - drop the shape check, and the A3 test fails;
  - rounds incremented on a retry, and the rounds test fails;
  - drop the receipt block check, and the tamper test fails;
  - skip a valid escape pair in the scan, and AC2 fails.
- **Full suite:** `scratchpad/suite-main.sh`, fail-closed, with 0 skipped.
- **Review:** a quality review and a test-engineer review of the diff before handback.

## Rollout

- A PR, then a release as v0.37.0, because this adds a feature: a receipt block and ledger events.
- Then reinstall. `v8-live-validation-2` attempt 2 follows under that run's existing plan amendments.
