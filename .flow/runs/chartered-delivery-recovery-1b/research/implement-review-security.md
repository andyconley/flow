# Implementation review (security): chunk 1b

- **Assignment:** `implement-review-security` (security-reviewer), read-only, over `7b2b7ff..d21a2d2`.
- **Counts:** 0 blockers, 1 major, 5 minors, 3 nits. No path lets a superseded attempt make a provider call: every v8 decide, consume, and send runs under `delivery_authority_guard` (`run_lock`), and a lead change holds `run_lock` from the ledger read through the `run.json` write.

## Findings

- **S-M1 (major, observed).** Receipt `lineage_usage` is only shape-checked (`cli/execution_contracts.py:356-370,959-965`). Tampering is caught only when it flips `retry_eligible`. Fix: require own paid + `predecessor_paid_calls` ≤ `max_paid_worker_calls`, and verifier reserved + `predecessor_verifier_sends` ≤ `max_verifier_calls`; the ledger stays authoritative.
- **S-m1 (minor, inferred).** The probe set and the seal set differ (`delivery_control.py:292-300`, `execution_ledger.py:365-371,390`). An attempt created between the two queries is sealed without its lock ever being probed. Attempts under another `work_id` are probed but not sealed. Fix: pass the probed IDs to the seal and refuse on any started v8 attempt outside that set; filter `started_v8_attempts` by `work_id`.
- **S-m2 (minor, inferred).** A prepare racing a lead change can create a started attempt under the stale claim. It cannot dispatch, but it blocks successors until the next lead change. Fix: prepare's lineage read and `create_attempt` under the authority guard.
- **S-m3 (minor, observed).** `KeyError`/`TypeError` from envelope parsing, and a non-`RecoveryRefused` `ContractError`, escape `_fence_and_seal_attempts` as exceptions (`delivery_control.py:293,301-304`). This is fail-closed, and all locks are released. Fix: map them to `lead_guard_ledger_unreadable`.
- **S-m4 (minor, inferred).** A missing ledger is treated as empty (`delivery_control.py:281-282`). A dangling symlink or a deleted ledger skips the guard. Fix: `lstat`; treat a symlinked ledger as unreadable; treat a missing ledger as unreadable when `execution/` already holds attempt directories.
- **S-m5 (minor, observed).** The legacy receipt fallback in `_v8_lineage_locked` hashes an unconfined absolute path with an unbounded read inside `BEGIN IMMEDIATE` (`execution_ledger.py:315-319`). Fix: confine the path to `<execution>/<attempt>/receipt.json`, open it with `O_NOFOLLOW`, and bound the size.
- **S-n1 (nit).** The seal releases grants without checking for dispatch events, and leaves `allowed` manager calls in place.
- **S-n2 (nit).** `consume_grant`, `consume_manager_grant`, and `prepare_verifier_send` don't check `attempts.status`. Safety rests on the authority guard.
- **S-n3 (nit).** `send_lock` lacks `O_NOFOLLOW` (carried over).

## Lock questions

The lock order is deadlock-free, since the probe never waits. No lock is left held on any error path. A seal followed by a failed claim write is safe for spend.
