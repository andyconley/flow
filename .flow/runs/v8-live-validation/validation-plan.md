# Validation Plan: v8 live validation

This run's proof is live evidence, captured as specified by AC9, with a verdict for each AC on each attempt (AC10).

| AC | How it is proven | Evidence captured |
|---|---|---|
| AC1 | `inspect-delivery` after `start-plan`: a v3 charter, the limits, headroom, and `delegated_expansion: true` | Inspect JSON (preflight) |
| AC2 | The launch JSON and envelope: protocol 8, the projected headroom, a roster of `docs-editor` and `local-verifier`, a Claude manager | `execution/<attempt>/envelope.json` fields |
| AC3 | Each receipt action's result has `physical_call: true` and a Claude or Ollama evidence level; manager calls are observed responses; there is no `local_stub` | Receipt extract |
| AC4 | The receipt `expansion` block and `expansion_state` show a `charter_headroom` grant (expected at manager call 5), with no pause at that point | `expansion_state` JSON |
| AC5 | The launch or resume returns `expansion_paused`; `flow run status` shows the next action; `decide-expansion` output; nothing is sent for the paused call (its status stays `denied` until the resume) | Status and inspect snapshots before and after, decision JSON |
| AC6 | After a resume, the paused `call_id` is `completed` once; manager-call sequences are contiguous; there are no duplicate sends; completed actions aren't re-sent (the Claude editor send count stays 1) | Ledger snapshot analysis |
| AC7 | `validate_receipt` passes; the ledger's `sealed_receipt_sha256` equals the file's sha256; the `expansion` block is complete | Script output |
| AC8 | The outcome classified as one of five: completed, legitimate failure, Flow defect, environmental failure, or no receipt | Classification with evidence |
| AC9 | Every item listed, recorded in `validation-results.md` | That file |
| AC10 | At most two attempts; a second one records why it was needed; the same sealed limits (plan amendment) | Attempt log |
| AC11 | If completed: `git diff --stat` shows only the four files; the targeted test passes; `test_flow.py` passes; a diff review is written | Diff stat, test output, review |

- **Preconditions:** the baseline test failure and the job charter sha256 are recorded before launch (A7, A8).
- **Mutation check:** not applicable. This run changes no Flow code; the live run is the test.
- **Validated against:** the change itself, meaning real providers on the installed v0.36.0 CLI. There is no surrogate.
