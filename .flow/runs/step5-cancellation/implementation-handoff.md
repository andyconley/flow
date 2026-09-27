# Implementation Handoff: step5-cancellation

**Read first:** `requirements.md` (revision 2), `acceptance-criteria.md`, `plan.md` (the commits and design decisions D1–D7), `definition-dispositions.md` and `research/spikes.md`.

## Rules

- **Commit order:** C1, then C2, C3, C4, C5, as Conventional Commits. The full suite must be green after each commit.
- **v8 only.** Protocols 5–7 behave exactly as before, and a v7 attempt sealed `unknown` still blocks a lead change.
- **Never resend or reclassify an uncertain row without evidence.** In every new seal, uncertain rows stay `unknown` or `started` in the ledger and in the receipt.
- **The ledger and the existing fences are authoritative.** Control records and cancel requests are identity or intent evidence only.
- **Lock order is unchanged (D6).** `cancel-delivery` holds no lock.
- **The signal handler only sets a flag**, and raises at most once, only inside `interruptible()`. Sealing happens in normal code after the stack unwinds.
- **Tests are hermetic.** Real subprocesses, process groups and signals are allowed. Synchronize with FIFOs, not sleeps. No paid or live calls.

## First step of C4

Confirm that provider callbacks run on the main thread. If they don't, apply the fallback in the plan's Risks section before writing the rest of C4.

## Test commands

- Focused: `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python python3.12 -m unittest tests.test_delivery_termination tests.test_process_identity tests.test_delivery_cancel`
- Full suite: `scratchpad/suite-main.sh`, which exits non-zero on any failure or skip.

## Done when

- AC1–AC12 pass.
- The six mutation checks in AC12 each fail their named criteria. Mutations are restored from file backups, never with `git checkout`.
- `validation-results.md` records every per-check verdict, including "Linux reader: parser-tested only".
