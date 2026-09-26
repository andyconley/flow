# Acceptance Criteria: manager progress repair and bounded retry

- **AC1, real-data regression.** The recorded failing reply from `v8-live-validation-2` attempt 1, kept as a test fixture, is **repaired**:
  - its object selects `local-verifier`;
  - MAF receives canonical JSON that `_extract_json` parses to the same object.
- **AC2, repair is exact.** Valid escapes (`\"`, `\\`, `\n`, `é`, and so on) are byte-for-byte untouched. A backslash before any other character is doubled. A `\u` not followed by 4 hex digits is also doubled (A4). The cases include an escaped backslash followed by a backtick, `\u12` and `\uZZZZ`. An already-valid reply is never marked repaired.
- **AC3, bounded retry.**
  - One unparsable reply followed by a valid one leads to 1 retry, 1 extra Flow-gated manager call, no change to `manager_round`, and the attempt continues.
  - Three unparsable replies in a row fail the attempt as `failed`, with the specific reason, and **no replan call follows** (A1).
  - A reply that parses but lacks the five ledger items as objects with an `answer` counts as unparsable (A3).
- **AC4, accounting.** A retry that exceeds `max_manager_calls` goes through ADR 0017 expansion: an automatic grant within headroom, or a pause for a decision. A retry past the runner ceiling is a hard denial.
- **AC5, parity.** The corpus covers valid, fenced, wrapped, Python-literal, invalid-escape and garbage replies, plus an instruction containing a fenced object (A5). On it, MAF's `_extract_json` and `_coerce_model`, applied to **the text Flow hands MAF** (the canonical form or the sentinel), agree with Flow's decision. This is MAF-gated.
- **AC6, replay identity.** An attempt that retried or repaired, then paused and was recovered, replays with identical call ids and rounds, and sends no duplicate manager call. This is MAF-gated.
- **AC7, audit.**
  - The receipt's `manager_progress` block is built from the completed progress-call rows, and is absent when there is nothing to report.
  - `validate_receipt` recomputes it, and rejects a tampered block, an empty block, or a block on a protocol version below 8.
  - Ledger events are written in the same transaction as the observation (A2).
- **AC8, no regressions.** The full suite passes with 0 skipped and `FLOW_MAF_PYTHON` set. The existing MAF end-to-end and expansion tests pass unchanged.
- **AC9, documentation.** ADR 0018 is written, and `docs/maf-adoption-design.md` refers to it.
