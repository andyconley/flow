# Validation Results: v8-live-validation

- **Date:** 2026-09-26.
- **Installed CLI:** flow v0.36.0.
- **MAF:** `~/.flow/venvs/maf` (core 1.19.0, orchestrations 1.2.0).
- **Worktree:** `~/src/flow-v8-live-job` at `c864241ab064faf706ab14f09fe7ca9c28daf3c0`.
- **Outcome:** the validation found two Flow defects. Attempt 1 ended as a **Flow defect with no receipt** (AC8). No second attempt was possible, as explained below.

## Preflight and baseline (evidence/preflight.txt, baseline-test.txt, inspect-preflight.json)

- **Environment:**
  - `gemma4:26b` was present and warmed (8.0 s load, `keep_alive` -1);
  - Claude was signed in (claude.ai);
  - the installed flow was v0.36.0, and its digests equaled the sealed ones;
  - the MAF interpreter imported, and the gated expansion tests passed with it.
- **Job charter:** its sha256 was `358eac06…515c`, matching the value frozen at `approve-plan` (A7).
- **Baseline test (A8):** failed as designed. The help and reference tests failed, and the sync test passed.
- **Contract proof:** the contract was shown to be satisfiable in a scratch copy, where all 3 tests passed.

## Attempt 1: `f628faa99c6e4e0e8d18de37a1572370` (evidence/launch-1.json, inspect-after-launch-1.json)

- **Timing and result:** the launch ran for 137 s and returned `interrupted`, reason `reconciliation_required`, detail "Claude edit output exceeds limit".
- **Ledger:**
  - manager calls 1 (facts), 2 (plan) and 3 (progress, which selected `docs-editor`) all completed, as real Claude calls;
  - action 1 (`docs-editor`, Claude) ended `unknown`, with reason `specialist_send_outcome_uncertain`;
  - there were no expansion requests: the run never reached manager call 5.
- **Cause (Flow defect D1):** `cli/claude_edit_worker.py` aborts once the Claude stream-json output passes `MAX_EVENT_BYTES` (1 MiB).
  - A normal edit session exceeded that. The tool results from reading the documentation files produced events of 52, 62, 99 and 144 KB, and the stream held 981 `stream_event` records.
  - Aborting mid-turn left the send uncertain, so Flow correctly fell back to marking it `unknown`, recording an interruption, and resending nothing.
- **Job observation (D2):** the producer's partial edit (`evidence/attempt-1-worktree.diff`) wrote the table row with `(--approve \| --deny)`, so the sync check would have failed.
  - This was despite the explicit instruction, but escaping is correct Markdown: a raw `|` splits a table cell when GitHub renders it.
  - The help generator (`scripts/regenerate-flow-help.py`) emits raw pipes, so existing rows such as `all|claude|codex` already render broken.
  - The defect is in the generator, not the producer.
- **Why no second attempt:**
  - the unknown action can only be abandoned, because Flow stored no response observation (ADR 0012, 0016);
  - an uncertain send blocks the lead supersede a successor needs;
  - a started sibling attempt blocks any new attempt.
- **Close-out:** the lead claim was released through `delivery_control.change_lead_claim(..., "release", expected_generation=1)`, which returned `ok True` (evidence/release.txt). There is no CLI for this (plan amendment).

## Verdict per acceptance criterion (attempt 1)

| AC | Verdict | Evidence |
|---|---|---|
| AC1 authority sealed | **Met** | v3 charter `7a2e250b…` with the sealed limits and headroom |
| AC2 live preparation | **Met** | A v8 attempt was prepared against the pinned worktree, with a roster of `docs-editor` and `local-verifier` and a Claude manager |
| AC3 real providers | **Partly met** | 3 real Claude manager calls completed. The producer's call was real but its outcome is unknown. The verifier was never reached. |
| AC4 automatic grant | **Not reached** | The run stopped at manager call 3 |
| AC5 escalation | **Not reached** | Same |
| AC6 identical replay | **Not reached** | Same |
| AC7 sealed valid receipt | **Not reached** | No receipt; v8 never seals as unknown |
| AC8 verdict | **Flow defect** (D1) | See above |
| AC9 evidence | **Met** | `evidence/` |
| AC10 attempt discipline | **Met** | One attempt; a second was not possible (see above) |
| AC11 documentation change | **Not applicable** | The job didn't complete |

- **Mutation check:** not applicable. This run changed no Flow code.
- **Validated against:** real providers on the installed v0.36.0. There is no surrogate.

## What the live run did prove

- **Preparation:** the sealed v3 authority, envelope projection, worktree containment, the clean baseline and the roster all worked live.
- **Manager:** the stock Magentic manager on Claude ran through Flow-gated calls, with Flow observing each response.
- **Producer:** Flow dispatched the Claude editor under a Flow grant, with write scope enforced by the edit worker.
- **Fail-closed behavior:** when a send's outcome was uncertain, Flow marked it `unknown` and recorded an interruption, and did not guess or resend.

## Follow-ups

1. **Fix run** (D1, D2):
   - let the Claude edit worker keep consuming the stream past the event-log cap, truncating only the stored log instead of aborting, with a test;
   - make the help generator escape `|` in table cells, and regenerate the tables.
2. **A fresh validation run** (`v8-live-validation-2`), reusing this definition, the job test and the runbook, after the fix is released.
