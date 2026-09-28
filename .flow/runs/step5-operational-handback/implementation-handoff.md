# Implementation Handoff: step5-operational-handback

**Read first:**
- `requirements.md` (revision 2, approved; R10 amended);
- `plan-dispositions.md`, and `plan.md` § "Amendments from plan review" (A1–A18), which override the design text where they conflict;
- `acceptance-criteria.md`;
- `plan.md`: interpretations I1–I6, commits C1–C7, design D1–D16;
- `validation-plan.md`;
- `research/spikes.md`.

## Rules

- **Commit order:** C1, then C2 through C7, as Conventional Commits. The full suite must be green, with 0 skipped, after each commit.
- **v8 only.**
  - Protocols 5–7 keep their event streams, receipts and limits unchanged.
  - `grant_changed`, manager identity, request files and tokens apply to v8 only.
- **Pre-release v8 attempts are read-compatible and write-refusing (I6).**
  - `inspect`, `stuck`, `trace` and `abandon` keep working on them.
  - Prepare, the gate and the seal refuse them.
- **The ledger and the existing fences are authoritative.**
  - The lock order is unchanged.
  - The token check adds no lock.
  - Request files and group lines are evidence, not authority.
- **One pure function per concept, shared everywhere:**
  - `charge` and `token_usage_block` (`execution_contracts.py`);
  - `compare_receipt_rows` (`receipt_compare.py`);
  - `render_manager_prompt` (`manager_requests.py`).

  Never copy their logic into the verifier or trace.
- **`trace` and `verify-receipt` never write**, and read the ledger in exactly one read transaction through `lineage_view`.
  - verify takes no lock and makes no subprocess call.
  - trace creates no lock file, but may use a non-blocking liveness probe (A13).
- **Existing event `detail` strings are unchanged.** `grant_changed` is written immediately before the event it accompanies.
- **Tests are hermetic.** Stub providers report the S1–S3 usage values. Stub process groups must be real child processes, never the test's own pid, because abandon reaps recorded groups. No paid or live calls.

## First steps

- **C1:** build the AC3 `SITES` table from `plan.md` D7 *before* adding emissions. The structural test then guides the work.
- **C4:** before writing the successor scenario in the fixture builder, compute the token numbers M, T and U and the per-call usage. Assert the plan's inequalities (the automatic tranche fires after the verifier; the second hit is on the final manager call; units = 1).
- **C6:** run SP-A (a `mode=ro` connection with `BEGIN` then `rollback` creates no journal file).

## Test commands

- **Focused:**

  ```
  FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python python3.12 -m unittest tests.test_grant_history tests.test_manager_requests tests.test_token_charge tests.test_token_gate tests.test_receipt_compare tests.test_receipt_verify tests.test_delivery_trace
  ```
- **Full suite:** `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python python3.12 -m unittest discover -s tests`, which must report 0 skipped.
- **Help:** `python3.12 scripts/regenerate-flow-help.py --check`.

## Done when

- AC1–AC23 (including AC12b and AC12c) pass.
- Mutations M1–M8 each fail their named tests.
- `validation-results.md` records:
  - every AC verdict;
  - the AC22 fixture-change list;
  - the AC23 mapping with real output;
  - the manual `v8-live-validation-3` checks (`unsupported_contract`, `unsupported_receipt`).
