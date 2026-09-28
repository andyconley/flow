# Planning spikes: step5-operational-handback

## S1. Codex reasoning tokens (F19): resolved [observed]

- **Source:** a real Codex session log under `~/.codex/sessions/2026/…` (a `token_count` record):
  - `total_token_usage`: `{"input_tokens":42377,"cached_input_tokens":25088,"cache_write_input_tokens":0,"output_tokens":258,"reasoning_output_tokens":138,"total_tokens":42635}`;
  - `last_token_usage`: `{"input_tokens":23537,"cached_input_tokens":18176,"cache_write_input_tokens":0,"output_tokens":119,"reasoning_output_tokens":56,"total_tokens":23656}`.
- **Totals:** `total_tokens = input_tokens + output_tokens` in both (42,377 + 258 = 42,635; 23,537 + 119 = 23,656).
- **Reasoning:** `reasoning_output_tokens` ≤ `output_tokens`, so reasoning is **included in** `output_tokens`. Charging `output_tokens` counts reasoning exactly once, and P1 needs no reasoning term.
- **Cache writes:** Codex also reports `cache_write_input_tokens`, which was 0 in every observed record. Its relationship to `input_tokens` is unobserved. The plan treats it as reported only, and the ADR says so. If a future record shows a non-zero value, the fixture test (AC9) documents the choice.
- **Fixture:** the Codex AC9 fixture uses the `last_token_usage` shape above, with the exact values. The `codex exec --json` `turn.completed.usage` is the same key set (`cli/normalize.py:84-110` reads the same keys).

## S2. Claude editor usage scope (F19): resolved [observed]

- **Source:** the `v8-live-validation-3` receipt (branch `codex/v8-live-validation-3`, `execution/def92b2b…/receipt.json`). The Claude editor result has:
  - `num_turns: 17`;
  - `usage = {input_tokens: 20, output_tokens: 4024, cache_creation_input_tokens: 78332, cache_read_input_tokens: 598695}`.
- **Scope:** 598,695 cache-read tokens over 17 turns is about 35k per turn, consistent with the conversation re-read on each turn. One turn couldn't produce it. So the `result` event's usage is the **session aggregate**, and P1 charges the whole editor session once.
- **Charge:** 20 + 78,332 + 4,024 = 82,376.
- **Fixture:** the Claude AC9 fixtures use these exact values (editor) and the six manager usages from the same receipt.

## S3. Calibration data (P10) [observed]

These are the charged values per call in the `v8-live-validation-3` lineage (a single attempt; the manager is Claude, the editor is Claude, the verifier is Ollama):

| Row | Charged | Cache read |
|---|---|---|
| manager 1 | 6,089 | 3,397 |
| manager 2 | 5,971 | 4,353 |
| manager 3 | 8,271 | 4,353 |
| manager 4 | 10,421 | 4,353 |
| manager 5 | 10,695 | 4,353 |
| manager 6 | 10,075 | 4,353 |
| editor (Claude) | 82,376 | 598,695 |
| verifier (Ollama) | 0 (not charged) | — |
| **Lineage** | **133,898** | |
