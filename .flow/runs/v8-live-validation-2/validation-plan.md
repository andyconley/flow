# Validation Plan: v8 live validation 2

This run's proof is live evidence, captured as AC9 specifies, with a verdict for each AC on each attempt (AC10).

| AC | How it is proven | Evidence captured |
|---|---|---|
| AC1 | `inspect-delivery` after `start-plan`: a v3 charter, the limits and headroom, and `delegated_expansion: true` | Inspect JSON (preflight) and `delivery/*/delivery-charter.json` |
| AC2 | The launch JSON and envelope: protocol 8, the projected headroom, a roster of `docs-editor` and `local-verifier`, and a Claude manager. The preflight records the fresh, clean worktree | `execution/<attempt>/envelope.json` and `evidence/preflight.txt` |
| AC3 | Each action result is a physical call with a Claude or Ollama evidence level, manager calls are observed responses, and there's no `local_stub` | Receipt extract |
| AC4 | `expansion_state` and the receipt's `expansion` block show a `charter_headroom` grant (expected at manager call 5) with no pause | Expansion JSON and timings |
| AC5 | `expansion_paused`, the `flow run status` next action, and the `decide-expansion` output. Nothing is sent for the paused call | Status and inspect snapshots before and after, decision JSON |
| AC6 | After resume, the paused id is `completed` exactly once, sequences are contiguous with no duplicate sends, and the Claude editor send count stays 1 | Ledger snapshot analysis |
| AC7 | `validate_receipt` passes, the ledger's `sealed_receipt_sha256` equals the file's sha256, and the `expansion` block is complete | Script output |
| AC8 | One outcome: completed, legitimate failure, Flow defect, environmental (with its error signature), uncertain send (released), or no receipt | Classification with evidence |
| AC9 | Every item, including the per-call timings from `scripts/ledger_timings.py` and the timed verifier gate | `validation-results.md` and `evidence/` |
| AC10 | At most two attempts, and an uncertain send is the last one. The limits are the same sealed ones | Attempt log |
| AC11 | If completed: the diff touches only the four files, the targeted test passes, `--check` is clean, `test_flow.py` passes, and a diff review is written | Diff stat, test output, review |
| AC12 | The producer turn ends with an observed terminal result and no worker-limit error. The event log size is recorded next to 1 MiB, with 0 `stream_event` records | Ledger events and event-log stats |

- **Preconditions:** the baseline test failure, the contract proof, the job charter sha256 and the verifier gate are all recorded before launch.
- **Mutation check:** not applicable. This run changes no Flow code, and the live run is the test.
- **Validated against:** the change itself, meaning real providers on the installed v0.36.1 CLI. There is no surrogate.
- **Evidence hygiene:** no symlinks in committed evidence.
