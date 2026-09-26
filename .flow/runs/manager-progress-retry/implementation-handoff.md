# Implementation Handoff: manager-progress-retry

- **Lane:** `flow-implement`, on branch `codex/manager-progress-retry`.
- **Read first:**
  - `plan.md`, the change map and commits;
  - `requirements.md` R1–R7;
  - `acceptance-criteria.md` AC1–AC9.
- **Fixture source:** the failing reply is `manager_calls[3].result.output` for attempt `22ab86c3559e4fd89e47cb9e59ebece2` in `.flow/runs/v8-live-validation-2/execution/ledger.sqlite` on branch `codex/v8-live-validation-2`. Copy it verbatim.
- **Invariants:**
  - roster, task, rationale and call-limit checks stay fail-closed;
  - replay is deterministic from recorded text;
  - ADR 0016 and 0017 semantics are unchanged;
  - v6 and v7 receipts keep their meaning;
  - no prompt changes.
- **Tests:** run `python3.12 -m unittest discover -s tests` with `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python`, fail-closed with no skips.
