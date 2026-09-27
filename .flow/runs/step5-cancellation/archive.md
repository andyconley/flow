# Archive: step5-cancellation

## Archive Summary

### Work Closed
- **Run:** `step5-cancellation`, MAF adoption step 5, slice 1. Merged as PR #45 (`ba2eda5`) and released as v0.38.0, which is installed and synced.
- **What changed:** operator and Shaper control over chartered v8 delivery attempts (ADR 0019).
  - **Terminal statuses:** new receipt-backed `cancelled` and `abandoned`. Each is sealed in one ledger transaction that keeps uncertain rows `unknown`, releases unconsumed grants, closes expansions and bumps the owner generation.
  - **ADR 0016 amended:** these statuses no longer block a lead change. A successor lists them as predecessors and counts their uncertain spend.
  - **Process identity:** a record for each dispatching parent, with its pid, a start time that doesn't depend on timezone, a hashed machine id, and every process group it starts.
  - **CLI:**
    - `cancel-delivery`: cooperative SIGTERM;
    - `abandon-delivery`: reaps recorded groups by identity, then seals;
    - `delivery-lead`: the four lead actions, with stable codes;
    - `stuck`: a read-only scan with the next command;
    - `inspect-delivery`: extended.
  - **Acceptance-review fixes** (`a16fea4`):
    - `reap` survives EPERM, skips the caller's group and leaders owned by another user;
    - a failed reap still seals or records an interruption;
    - a stale cancel request is cleared when the next parent starts;
    - ADR 0019 now says tamper resistance rests on `.flow` being unwritable, and notes the successor worktree reset.
- **First real use:** the stuck `v8-live-validation` attempt `f628faa9` was sealed `abandoned` (`84b4d8d`). Its unknown paid send stayed `unknown`, and `flow run stuck` is now empty.

### Validation
- **Automated:**
  - Full suite: 1,643 tests OK, 0 skipped, with `FLOW_MAF_PYTHON`.
  - The new modules ran twice with no flakiness.
  - Mutations M1–M6 are caught.
  - The five acceptance-fix tests each fail with their fix reverted.
  - PR #45 CI is green.
- **Manual:**
  - Quality, test and security reviews ran in both the implement and review lanes, with no Critical findings (`review.md`).
  - AC11 docs were checked, and the help check is up to date.
  - The acceptance orchestration gate passed after Andy amended the sealed manifest's producer list.
- **Runtime/deploy:**
  - Release v0.38.0 is verified by the workflow, installed with `flow update`, and the Claude and Codex adapters are re-synced.
  - The live abandon on this checkout's real ledger succeeded.

### Residual Risks
- The Linux `/proc` start-time reader is parser-tested only, and pidfd signalling is not exercised.
- On macOS there is a microsecond window between the closed-marker re-check and the signal.
- Tamper resistance depends on `.flow` being unwritable to workers. A forged control record can name any group the user owns.
- A request left by a CLI killed mid-cancel can still count within that run. A CLI timeout can report `cancel_timeout` for an attempt that did seal.
- A successor needs the worktree reset after a producer edited it. This is documented but not surfaced by `inspect-delivery`.
- Real Codex, Claude and Ollama are unexercised by these tests.

### Follow-up Work
- Backlog "Delivery Termination Follow-Ups": successor worktree drift, ledger-mirrored group registration, `change_lead_claim` codes, multi-writer and Linux hardening, cancel reporting, Linux validation.
- Remaining step 5 slices: trace correlation, receipt verification, MCP handback, token cap.
- `v8-live-validation-3`, with a new work id. It is paid and needs Andy's go. Reset `~/src/flow-v8-live-job-2` to `d6d771f2` first.

### Capability Gaps Observed
- The acceptance-review fixes ran inside `reviewing`, with no rework transition.
- Writable definition-lane (research) assignments missing from the producer list surfaced only at the acceptance gate, after the manifest was sealed. Closing it needed a hand amendment of a sealed artifact.
- Read-only review roles couldn't run the test suites they were asked to run, so the coordinator ran them.
- Revert-and-rerun proof for the new review-fix tests was scripted by hand.
- **Ledger:** all four gaps reuse existing keys:
  - `review-rework-transition`;
  - `handback-orchestration-producer-inventory`;
  - `reviewer-role-command-execution`;
  - `mutation-check-harness`.
- **Repeats:**
  - `review-rework-transition`: 13 (promoted);
  - `reviewer-role-command-execution`: 7 (promoted);
  - `mutation-check-harness`: 4 (promoted);
  - `handback-orchestration-producer-inventory`: 2 (open, can be promoted).

### Memory Updates
- **STATE (`.flow/memory/STATE.md`):**
  - `step5-cancellation` moves from active work to recently completed, as released in v0.38.0.
  - The next step is `v8-live-validation-3`.
- **Runtime memory entries written:** `project-flow-delegated-expansion` is updated with step 5 slice 1: the cancel and abandon commands, the stuck attempt abandoned, and v0.38.0.
