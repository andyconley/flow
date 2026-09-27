# Validation Plan: v8 live validation 3

This run's proof is live evidence, captured as AC9 specifies, with a verdict for each of AC1–AC13 on each attempt (AC10).

| AC | How it is proven | Evidence captured |
|---|---|---|
| AC1 | `inspect-delivery` after `start-plan` shows the v3 charter `756f6503…`, the limits and headroom, and `delegated_expansion: true` | Inspect output (preflight), `delivery/*/delivery-charter.json` |
| AC2 | The envelope has protocol 8; `expansion_headroom` equals `{delegations: 1, manager_calls: 1, paid_worker_calls: 1, verifier_calls: 1}`; the roster is `docs-editor` and `local-verifier`, with a Claude manager. The worktree is clean at `d6d771f2`, including after any reset | `execution/<attempt>/envelope.json`, `evidence/preflight.txt` |
| AC3 | Physical Claude and Ollama evidence for every call, and no `local_stub` | Receipt extract |
| AC4 | A `charter_headroom` grant with no pause: manager call 5 in attempt 1, or any key in a successor | Expansion JSON, timings |
| AC5 | `expansion_paused`, the status next action and the decision output; nothing sent while paused | Before and after snapshots, decision JSON |
| AC6 | The paused id completes once, sequences are contiguous with no duplicate sends, and the paid send count matches. D4-retry status is recorded | Ledger analysis |
| AC7 | `validate_receipt` passes, the sealed sha256 matches, and the expansion block is complete | Script output |
| AC8 | Exactly one outcome per attempt, including the new model-behaviour outcome, classified with evidence | Classification |
| AC9 | Every listed item, including the timings and the verifier gate | `validation-results.md`, `evidence/` |
| AC10 | At most two attempts. For a successor: the reset evidence, the verifier precondition, and the predecessor digest in the envelope | Attempt log, envelope |
| AC11 | If completed: the diff touches only the four files, the tests and `--check` are clean, `test_flow.py` passes, and a diff review is written | Diff stat, outputs |
| AC12 | D1, D3, D4, D5, D6 and D7 each checked as listed in plan step 12 | Ledger events, event-log stats, receipt blocks |
| AC13 | `stuck` and `abandon`/`cancel` outputs and receipt checks, if any attempt stopped without sealing; otherwise not applicable | CLI output, receipt check |

- **Preconditions before any launch:** the baseline test failure, the job charter sha256, the verifier gate (under 30 s), and `stuck` empty for this work id.
- **Mutation check:** not applicable. There's no Flow code change, and the live run is the test.
- **Validated against:** the change itself, meaning real providers on the installed v0.38.0.
- **Evidence hygiene:** no symlinks in committed evidence.
