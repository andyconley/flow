# Scout Summary: ollama-verifier-think

- **Branch:** `codex/ollama-verifier-think`, from `origin/main` at v0.36.1.
- **Fixes:** D3, found by `v8-live-validation-2` at its preflight verifier gate (evidence: `.flow/runs/v8-live-validation-2/evidence/d3-verifier-thinking.txt`).

## Scope

- **The fix** (`f8e8c18`, `fix(cli)`, in `cli/local_worker.py`): every Flow Ollama `/api/chat` request now sends `"think": false`.
  - **Why:** `gemma4:26b` is a reasoning model. On a real four-file diff (3,298 prompt tokens), its hidden reasoning used the whole 1,024-token `num_predict` budget, so `message.content` came back empty and the structured verifier could never pass.
  - **Other models:** `llama3.1:8b` was checked, and it accepts and ignores the field.
  - The older non-structured path (256 tokens) gets the same protection.
- **Tests** (`tests/test_execution.py`):
  - the existing HTTP-request test now asserts `think` is false;
  - a new test, `test_structured_verifier_request_disables_thinking`, checks `think`, `format` and `num_predict` on a structured verifier request.

## Validation

- **Targeted tests:** `tests.test_execution` passes in full.
- **Mutation check:** caught. Removing the field fails both tests.
- **Live, local and free:** through the repo's `call_local` with `structured_verifier=True`, the real verifier prompt (the `quality-reviewer` instructions plus the first run's diff) and `gemma4:26b`, 3 of 3 replies were schema-valid JSON. They took 11.7 s, 1.7 s and 1.9 s, with 110–136 output tokens. Before the fix the same request gave empty content after 13.7–16.7 s, having hit the token limit.
- **Full suite:** 1,544 tests OK, 0 skipped, with `FLOW_MAF_PYTHON`.

## Handback

- **Outcome:** ready for a PR. Releasing it as v0.36.2 unblocks `v8-live-validation-2`, which is paused at its launch gate with no attempt created.
  - The sealed specialist digests are unaffected, because this changes only call code.
  - The run's `scripts/verifier_gate.py` must add `"think": false` so it keeps matching Flow's request.
- **Caveat:** thinking is disabled for every Flow Ollama call. That's intended: Flow reads only the `content`, and the verdict schema has its own `summary` and `findings`.
- **Capability gap:** `local-verifier-realistic-load-check`. The verifier's live acceptance check used inputs much smaller than a real job's, so the token budget was never tested at realistic size.
