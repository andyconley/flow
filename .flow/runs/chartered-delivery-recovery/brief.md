# Definition brief: chartered delivery resume and recovery

- **Work ID:** `chartered-delivery-recovery`
- **Lane:** define
- **Opener:** solution-architect. This is a platform capability.
- **Engineer decisions (2026-09-23):**
  - Target this increment rather than delegated expansion approval, the live verifier proof, or operator controls.
  - Define now, and implement only after the protocol-v8 branch (`codex/structured-verifier-contract`, accepted, not merged) lands on `main`.

## Problem

A chartered delivery attempt (protocol v6, v7, or v8) cannot resume or be reconciled into continued execution. Only v5 can:

- `resume_delivery` and `recover_delivery` accept v5 only (`cli/delivery_gateway.py:584` and `:675` on the v8 branch).
- Chartered attempts are never marked `interrupted`. The gateway's interruption path excludes them.
- A crash, fence, or `unknown` provider outcome mid-attempt therefore leaves a chartered attempt stuck in `started` or `unknown`. It needs operator reconciliation and cannot continue.

This blocks unattended delivery. It is also a prerequisite for any mid-run pause, such as Shaper delegated expansion approval, which is the next vision step in `docs/maf-adoption-design.md`, adoption step 5.

## Evidence inventory

The v8 code is in `/Users/andyconley/.codex/worktrees/verifier-contract/flow`, and this run's artifacts are in `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`.

- **Recovery machinery (v5):**
  - `cli/delivery_gateway.py`: `resume_delivery` (~567), `recover_delivery` (~660), and `_execute_prepared_delivery` (~740) with its `initial_snapshot` re-verification (~767).
  - `cli/execution_ledger.py`: `mark_unknown`, `resolve_unknown` (~889), continuation epochs (`observe_continuation_response` ~1482), and owner generation fencing.
  - `cli/maf_supervisor.py`: checkpoint resume.
- **Chartered authority:**
  - `cli/delivery_control.py`: lead-claim change and supersede, and `delivery_authority_guard`.
  - `cli/delivery_contracts.py`, `cli/delivery_projection.py`.
  - ADR 0014: fenced generations. Resume or supersede must be explicit; elapsed time never transfers ownership.
- **Verifier state (v8):**
  - `cli/verifier_contracts.py`, and the ledger `verifier_inputs` and `verifier_evaluations` tables.
  - Replay re-evaluation in the gateway on-action replay branch.
  - The stale-evidence gate near `delivery_gateway.py:999`.
- **ADRs:** 0011 (gateway ownership), 0012 (Flow-owned MAF recovery), 0014, 0015 (all under `docs/adr/`).
- **Design:** `docs/maf-adoption-design.md`, especially the "Issues to solve" rows on checkpoint and ledger state.
- **Predecessor runs** (archives in `/Users/andyconley/src/flow/.flow/runs/`, manually inspected because archive retrieval was unavailable):
  - `maf-restart-reconciliation`
  - `maf-post-resolution-continuation`: a fenced continuation epoch, pinned checkpoint restore, no-dispatch grant, and a linked receipt.
  - `maf-runtime-control-recovery`
  - `maf-multiturn-recovery`
- **Latest runs:** `.flow/runs/structured-verifier-contract/archive.md` on the v8 branch lists v8 resume as the top follow-up. It notes that the targeted test's output includes timing, so re-running the test changes its digest; recovery must reuse recorded test evidence.

## Constraints known so far

- Flow stays the authority. Magentic checkpoints are execution evidence, not authority.
- Never resend a provider call whose outcome is uncertain. `unknown` requires evidence-backed resolution.
- v5 behavior and the historical meaning of v6 and v7 must not change.
- The work must fit Flow's C-lite run protocol and standard-library CLI.
