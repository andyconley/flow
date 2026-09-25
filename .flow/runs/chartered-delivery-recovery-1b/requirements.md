# Requirements: Chartered v8 Delivery Recovery, chunk 1b

- **Parent run:** `chartered-delivery-recovery` (archived; chunk 1a merged as PR #26). This run carries the parent's approved requirement 10 (lead authority) and risk R4 (limits across a lineage). The parent's `requirements.md`, `solution.md`, `plan.md` and `research/plan-architecture.md` (items 8–10) are the source of truth; this file records only the 1b slice and the decisions taken after 1a.
- **Why a linked run:** the lifecycle has no path from `review_accepted` back to `implementing`, so 1b cannot be a second cycle of the parent (engineer decision, 2026-09-23).

## Problem

After 1a, an interrupted v8 attempt that cannot be recovered (for example `no_restorable_checkpoint`) has only one remedy: a Delivery Lead resume or supersede followed by a fresh successor attempt. Today that remedy is unsafe or impossible:

- `change_lead_claim` guards on `pending_unknown_actions`, a field nothing writes, so a lead change is never blocked by an uncertain send.
- A lead change leaves the old attempt `started` in the ledger, so nothing fences it as terminal.
- A successor attempt has no link to its predecessors, so it gets a fresh paid-call and verifier budget (R4).

## Requirements (from parent requirement 10 and R4)

1. **Superseded seal.** A Delivery Lead `resume` or `supersede` first seals every `started` **v8** attempt of the run whose lead generation is at or below the outgoing generation as terminal `superseded`, before the claim generation changes. Unconsumed grants are released. v5, v6 and v7 attempts are not touched.
2. **Ledger-backed lead guard.** A lead `resume` or `supersede` is refused while any action or manager call in the run's ledger is `started` or `unknown`. The guard fails closed when the ledger exists but cannot be read. A run with no ledger yet is not blocked.
3. **Live-run fence.** A lead `resume` or `supersede` is refused with `attempt_running` while a live process holds a `started` v8 attempt's `recovery_lock`. Nothing is mutated.
4. **Abandonment stays available.** `attention` and `release`, and the lifecycle `pause` and `block` transitions, stay unguarded while actions are `unknown`.
5. **Successor lineage.** A new v8 attempt lists every earlier v8 attempt of the run in its envelope `predecessors`. `create_attempt` requires the list to equal the ledger's v8 attempts for the run exactly. A predecessor that is still `started` blocks `prepare` with `sibling_attempt_not_terminal`. The first attempt's envelope stays byte-identical (no `predecessors` key).
6. **Limits across a lineage.** Predecessors' paid worker sends and verifier sends count against the successor's charter caps. The verifier retry rule stays per attempt. `max_manager_calls` stays per attempt (parent decision P2). The receipt gains `lineage_usage` when predecessors exist.
7. **Task facts.** The manager's task facts gain one line per predecessor.

## Engineer decisions (2026-09-23, after 1a)

- **E1.** Track 1b as this linked run; chunk 2 gets its own linked run.
- **E2.** The positive supersede test uses an attempt with no `unknown` actions. The case where a resolved `unknown` unblocks a lead change moves to chunk 2, when v8 resolution exists.
- **E3.** The superseded seal applies to v8 attempts only. ADR 0016's "v7 or v8" wording is corrected.
- **E4.** A predecessor's lead generation may equal the successor's (`<=`, relaxing the merged validator's `<`). Retrying after a failed or completed attempt keeps working without a lead change, and its spend still counts against the caps.
- **E5.** A lead change refuses with `attempt_running` while a live process holds an attempt's `recovery_lock` (requirement 3).

## Out of scope

- A CLI command for Delivery Lead resume or supersede (operator-controls increment); enforcement is at the existing function.
- Resolving v8 `unknown` sends (chunk 2).
- Any change to v5–v7 semantics.
- Resetting the worktree for a successor: the existing `prepare` baseline check already requires the charter baseline (parent `solution.md`: "the successor starts fresh from the charter baseline").

## Approval status

- Derived from the parent's approved requirements; decisions E1–E5 approved by the engineer on 2026-09-23.
