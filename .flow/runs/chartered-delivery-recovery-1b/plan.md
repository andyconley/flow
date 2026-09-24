# Plan: Chartered v8 Delivery Recovery, chunk 1b

Source design: parent `research/plan-architecture.md` items 8–10, amended by decisions E1–E5 (`requirements.md`). Anchors below were re-read on `main` at `7b2b7ff`.

## Current state (observed)

- `cli/delivery_control.py:239` — the lead guard reads `current["pending_unknown_actions"]`, which nothing writes. `change_lead_claim` holds `run_lock` and writes the new claim and `run.json`; it never touches the ledger.
- `cli/execution_ledger.py:483` — `_unresolved_action(db, attempt_id)` already finds `started`/`unknown` actions and manager calls for one attempt. `resolve_unknown` (`:1089`) moves an action out of `unknown`, so the v5–v7 resolution path can clear the guard.
- `cli/execution_ledger.py:226` — `recovery_lock` is non-blocking and raises `attempt_running` or `recovery_in_progress`. A probe from inside `run_lock` inverts the documented order but cannot deadlock, because it never waits.
- `cli/execution_contracts.py:329-353` — `_validate_predecessors` merged in 1a with statuses `{completed, failed, denied, superseded}` and `lead_generation < generation`. It is called only when the key is present.
- `cli/delivery_gateway.py:239-421` — `prepare_chartered_delivery` mints the envelope and calls `create_attempt`; it does not read earlier attempts. Its baseline check already requires the charter baseline, so a successor needs a reset worktree (no change).
- `cli/execution_ledger.py:510-647` (`decide`) and `:428` (`_v8_limit_reason`, used by `regrant_recovered_action`) hold two copies of the v8 limit rules; `_verifier_usage` (`:1006`) and the receipt recompute (`cli/execution_contracts.py:935-947`) compute `retry_eligible`.
- `cli/delivery_projection.py:72` and `cli/flow.py:1028` already report `predecessors` from the envelope.
- Tests that change meaning: `tests/test_chartered_delivery_recovery.py:140` (AC9.1) — after 1b a supersede seals the attempt, so it would refuse `attempt_terminal`; the AC9.1 fixture moves to bumping `run.json` directly (the parent plan's test-21 fixture). `tests/test_chartered_delivery_gateway.py:253` supersedes a prepared attempt and must still block the worker.

## Changes

1. **Ledger (`cli/execution_ledger.py`).**
   - `lead_change_blocker() -> str | None` (read-only open): the first `started`/`unknown` action or manager call across all attempts.
   - `started_v8_attempts(*, max_lead_generation)`: attempt ids to fence.
   - `seal_superseded_attempts(work_id, *, lead_generation, successor_generation, action)`: under `send_lock` and `BEGIN IMMEDIATE`, re-check no unresolved row, then for each `started` v8 attempt with claim generation ≤ `lead_generation`: release `allowed` grants as `not_dispatched/superseded_unconsumed_grant`, set `status='superseded'`, `reason=canonical({...})`, `receipt_path=NULL`, and write `attempt_superseded`. Idempotent.
   - `v8_lineage(work_id)`: `[{attempt_id, terminal_status, receipt_sha256, lead_generation, status}]` in creation order.
   - `create_attempt`: for v8, inside the transaction, refuse `sibling_attempt_not_terminal` if an earlier v8 attempt is `started`, and `predecessor_link_invalid` unless `envelope.get("predecessors", [])` equals the ledger lineage exactly.
   - `_lineage_usage(db, envelope)`: predecessor paid sends (status `started|completed|failed|unknown`) and verifier sends (`_verifier_usage(pred).consumed`). Used in the `decide` v8 branch, `_v8_limit_reason`, and `_verifier_usage` (`retry_eligible` uses `reserved + predecessor_verifier_sends < maximum`). The retry rule stays per attempt.
2. **Lead control (`cli/delivery_control.py`).** For `resume`/`supersede` only, inside `run_lock`: if `execution/ledger.sqlite` exists, open it read-only (unreadable → refuse `lead_guard_ledger_unreadable`); refuse `reconciliation_required` on a blocker; hold each started v8 attempt's `recovery_lock` (non-blocking, via `ExitStack`; refuse `attempt_running`/`recovery_in_progress`); seal; then write the claim and `run.json` as today. The ledger import stays lazy. Errors keep the `(False, current, [reason])` shape.
3. **Contracts (`cli/execution_contracts.py`).** `_validate_predecessors` accepts `lead_generation <= generation` (E4). A v8 receipt with predecessors requires `lineage_usage: {predecessor_paid_calls, predecessor_verifier_sends}` (ints ≥ 0) and forbids it otherwise; the usage recompute adds `predecessor_verifier_sends` to `retry_eligible`.
4. **Gateway (`cli/delivery_gateway.py`).** `prepare_chartered_delivery` reads the lineage (read-only when the ledger exists), refuses `sibling_attempt_not_terminal`, and adds `predecessors` only when non-empty. `_build_receipt` adds `lineage_usage`. Task facts gain "Predecessor attempt <id> ended <status> under lead generation <n>; its evidence is not reused."
5. **ADR 0016.** Correct the amendment: v8 only (E3), `<=` (E4), the live-run fence (E5), and the new reason codes.

## Commit sequence

1. `docs(adr): narrow the ADR 0016 lead-change amendment to v8`.
2. `feat(delivery): seal superseded v8 attempts and guard lead changes on the ledger` — AC9.2–9.4; moves the AC9.1 fixture.
3. `feat(delivery): link successor attempts and count limits across the lineage` — AC lineage link and limits.
4. Validation evidence (no repository file).

## Risks

- **L1.** A v8 attempt left `unknown` blocks lead changes until chunk 2 adds v8 resolution. Accepted: that is the guard's purpose; abandonment stays available.
- **L2.** `lineage_usage` in a receipt is self-reported; the ledger is authoritative (same stance as R2).
- **L3.** The in-`run_lock` recovery-lock probe inverts the documented lock order. It is non-blocking, so it cannot deadlock; the ADR records it.
