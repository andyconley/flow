# Validation Plan: step5-operational-handback

## Acceptance criteria mapped to tests

| AC | Test location | Kind |
|---|---|---|
| AC1 | `tests/test_manager_identity.py` (new) | Gateway: stub manager replies with and without the identity fields. Validator: a receipt row with a field missing. |
| AC2 | `tests/test_manager_requests.py` (new) | Pure file tests (link-into-place, conflict, a mid-write fault, orphans). Gateway fault injection between the write and `consume_manager_grant`. Claude `input_sha256` recomputation. |
| AC3 | `tests/test_grant_history.py` (new) | `ast` enumeration of the `execution_ledger.py` write sites against the `SITES` table (plan D7), plus one scenario per op, plus a history replay on the boundary-b recovery scenario. |
| AC4 | `tests/test_process_identity.py` | A group line with `row_id`. The default adapters bind the id per call. |
| AC5 | `tests/test_chartered_delivery_recovery.py` | Link `previous_checkpoint_id`, including after quarantine. |
| AC6 | `tests/test_delivery_termination.py` (CLI through `flow.main`) | Missing `--actor` exits non-zero, and the run is byte-identical. The actor is recorded. A grep assertion on `cli/`. |
| AC7 | `tests/test_delivery_trace.py` (new) | Stub-driven rows (C2). Banner goldens (C4, paused state from the fixture builder). Fixture-lineage rows and totals (C6). Pinned JSON schema. Digests of every file before and after. |
| AC8 | `tests/test_shaper_delivery_contracts.py`, `tests/test_chartered_delivery_gateway.py` | Contract refusals, projection, prepare refusal, `DEFAULT_TOKEN_BUDGET` pinned to P10 (I1). |
| AC9 | `tests/test_token_charge.py` (new) | A table test of the pure `charge`. Fixture values are copied exactly from `research/spikes.md` S1 (Codex `last_token_usage`) and S2/S3 (Claude editor and managers). |
| AC10–AC12c | `tests/test_token_gate.py` (new) | Ledger-level tests: every grant path, the just-under case, the automatic tranche, the escalation with no manager send between pause and decision (by seq), the shortfall of more than one tranche on both paths, and concurrent overshoot with `max_concurrent` 2. The end-to-end escalation goes through the MAF fixture builder. |
| AC13 | `tests/test_token_gate.py` | A successor over an abandoned predecessor with an `unknown` send. A superseded predecessor. |
| AC14 | `tests/test_chartered_execution_contract.py` | `validate_receipt` recomputes `token_usage`, with a field-by-field edit loop. Seal refusals. |
| AC15–AC19 | `tests/test_receipt_verify.py` (new) | The fixture lineage from `tests/delivery_handback_fixture.py` (new), built once per class and copied per case. |
| AC20 | `tests/test_receipt_compare.py` (new), `tests/test_delivery_termination.py` | Both seals refuse content, row and key differences. An identity assertion checks that one function is shared. The snapshot is taken under `send_lock` (a hook asserts the lock is held). |
| AC21 | Manual check plus `regenerate-flow-help.py --check` | ADR 0020 checklist against the R17 items. |
| AC22 | Full suite | `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python python3.12 -m unittest discover -s tests`, with 0 skipped. Every fixture change is listed in `validation-results.md`. |
| AC23 | `validation-results.md` | The `reconciliation.md` mapping, each row shown by a named check in real `verify-receipt` and `trace` output from the fixture. |

## AC16 tamper cases

These are the exact changes and the expected failing sets. They refine the AC16 table as that AC allows; the reasons are recorded here.

| Tamper | Exact change | Expected failing checks |
|---|---|---|
| Byte-only receipt change | append a space | {V1} |
| Receipt content change | `manager_calls[0].observed_at` | {V1, V3} |
| Ledger action result, same status (a) | the editor row's `result.session_id` | {V3} |
| Ledger action result, same status (b) | `result.usage.output_tokens += M` | {V3, V4, V17} |
| Envelope limit changed | `max_runtime_seconds` in the **ledger** `envelope_json` | {V2, V7}. Changing only the `envelope.json` file fails {V2}, tested as its own case. |
| Charter file content changed | a canonical-content change, not whitespace, since digests are over canonical content | {V7} |
| Requirements snapshot changed | one byte | {V8} |
| Checkpoint byte changed | one byte | {V9} |
| Request file message changed | a message text | {V10} |
| `repair.diff` byte changed | one byte | {V11} |
| Trace byte changed | one byte | {V14} |
| `baseline.json` field changed | one field | {V13} |
| Duplicated `manager_send_started` | INSERT a copy into `events` | {V15}. V17 uses the first send-start. |
| Predecessor receipt byte changed | whitespace | {V6} |
| Group line row id changed | a provider line | {V16} |
| A `grant_changed` event deleted | the paid row's `op=issue` | {V15, V17} |

Each case asserts:
- the exact failing set;
- that every other check keeps its clean status;
- that each failure's detail names the row or field and both values (or digests, plus the first differing path).

## Requiredness and no-vacuous-pass

- `REQUIREDNESS` in `cli/receipt_verify.py` is a direct encoding of the R14 table. A test compares it cell by cell against a literal copy of the table.
- For each `R` cell, a case removes the check's input and expects `fail`.
- For each `P` cell, a case removes the input and expects `not_applicable` with its fixed reason.
- For the cancelled and abandoned fixtures, every `—` and absent `P` check must give its fixed `not_applicable` reason.

## Read-only and offline (AC18)

- Every file under the run directory (including locks and any `-journal` or `-shm` files) is hashed before and after `trace` and `verify-receipt`.
- `subprocess.Popen`, `socket.socket` and `urllib.request.urlopen` are patched to raise, and the run must still complete.
- The number of `ExecutionLedger._db` calls is counted: exactly one, via `lineage_view`.
- SP-A, run first in C6: confirm that a `mode=ro` connection with `BEGIN` then `rollback` creates no journal file.

## Mutation checks

Each mutation is applied to production code from a file backup and restored from that backup (never with `git checkout`). Each must fail its named tests:

| # | Mutation | Must fail |
|---|---|---|
| M1 | Drop the `token_cap` entry from `_v8_action_checks` | AC10, AC11, AC12 |
| M2 | `_v8_manager_checks` stops excluding the reissued row | AC10 (reissue) |
| M3 | `charge` returns 0 for `unknown` rows | AC9, AC13, V17 cases |
| M4 | The token predicate multiplies by 1 instead of `token_tranche`, reintroducing F1 | AC12 |
| M5 | `compare_receipt_rows` compares status only | AC20, AC16 (ledger-result cases) |
| M6 | verify-receipt `pass` with `compared == 0` allowed | AC17 |
| M7 | Write the request file after `consume_manager_grant` | AC2 (fault injection) |
| M8 | Remove one `grant_changed` emission | AC3 (structural and scenario) |
| M9 | Drop the V15 transition check | AC16 (`grant_changed` deleted) |
| M10 | Drop the token check from `_v8_manager_checks` | AC10 (manager path) |
| M11 | Reintroduce a hard `token_cap` refusal at 0 headroom | AC10 (amended) |
| M12 | V17 counts rows sent after the issue seq | AC15 (clean fixture fails) |
| M13 | Remove the legacy refusal in `_v8_action_checks` | the I6 refusal tests |

## Runtime

- No live or paid calls; the live exercise is `v8-live-validation-4`.
- `trace` and `verify-receipt` are also run once, by hand, against the committed `v8-live-validation-3` run, checked out from its branch. The expected results:
  - trace prints the rows, and marks the contract `unsupported_contract`;
  - verify-receipt exits 2 with `unsupported_receipt`.

  This confirms that I6 and P9 hold on a real pre-release run.

## Notes from the plan review

- **AC19 and V13 (A12).** On cancelled and abandoned fixtures V13 **passes**, because `baseline.json` is always written at prepare. Only V11 and V12 are `not_applicable`.
- **Added cases (A4, A5, A18):**
  - AC9: a Codex usage with a nested extra key, and a manager usage with a string extra key;
  - AC2: a kill after the temp file is created;
  - AC1: a Codex manager `thread_id`;
  - AC16: a ledger envelope edited to the legacy key set while `envelope.json` stays supported, which fails V2.
- **Goldens (A18).** Seq and time are normalised in the banner goldens.
