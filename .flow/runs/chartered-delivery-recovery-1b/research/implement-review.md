# Implementation review (quality): chunk 1b

- **Assignment:** `implement-review-quality` (quality-reviewer), read-only, over `7b2b7ff..d21a2d2` excluding `.flow/`.
- **Verdict:** approve. One major test-strength fix is recommended before merge; there are no blockers.

## Brief questions

1. **No mutation on refusal (observed):** guard, unreadable ledger, live lock, sibling, and link mismatch. Only lock files change.
2. **Cap evasion (observed):** closed by the exact in-transaction lineage comparison, the serialized prepares, the envelope-change refusal in `decide`, and the lineage count in the regrant path. `regrant_not_dispatched` has no lineage count; it is unreachable for v8 until chunk 2.
3. **Agreement (observed):** `decide`, `_v8_limit_reason`, `_verifier_usage`, and the receipt recompute agree, and the retry rule stays per attempt.
4. **v5–v7 and byte identity (observed):** held. One intended shift: a v7 `unknown` send now blocks a lead change (requirement 2); the ADR should say so.
5. **Locks (observed):** probes never wait, `send_lock` comes after `run_lock`, and the `ExitStack` releases on every path.

## Findings

- **Q-M1 (major, observed).** The "retry disagrees" tamper case in `tests/test_chartered_delivery_recovery.py` also flips `retry_eligible` on a `valid_pass` successor. It fails on that flag alone, so tampering with `lineage_usage` alone is not shown. The validator only checks shape. Fix: use a `valid_fail` successor where the lineage flips eligibility, tamper only the count, and add cap-bound checks.
- **Q-m1 (minor, inferred).** `prepare_chartered_delivery` reads the lead generation without `run_lock`. A racing lead change can leave a stale `started` attempt that blocks successors. Fix: `create_attempt` under the authority guard.
- **Q-m2 (minor, observed).** `ContractError`, `KeyError`, and `TypeError` escape `_fence_and_seal_attempts` and break the return shape.
- **Q-m3 (minor, observed).** The seal leaves `allowed` manager grants and the owner generation unchanged. Fix: release them or bump `owner_generation`.
- **Q-m4 (minor, observed).** `started_v8_attempts` does not filter by `work_id`, but the seal does.
- **Q-m5 (minor, observed).** Test gaps: a `started` action or an `unknown` manager call as the guard trigger; `_v8_limit_reason`'s lineage count; an altered `lead_generation` link.
- **Nits.** Comment why predecessor paid sends exclude `not_dispatched`; the legacy receipt fallback resolves relative paths against the current directory; the writable ledger constructor runs DDL on the post-probe path.

## Scope

No drift into chunk 2. Chunk 2 must add the lineage count to `regrant_not_dispatched` and to any v8 resolution regrant.

## Dispositions (both reviews), fixed in `e16e8bd`

| Finding | Disposition |
|---|---|
| Q-M1 / S-M1 `lineage_usage` shape-only | **Fixed.** Own sends plus lineage are bounded by the paid and verifier caps. `test_tampering_only_lineage_usage_fails_receipt_validation` changes only `lineage_usage` on a `valid_fail` successor where the lineage flips eligibility. Mutation M3 fails it. The ledger stays authoritative (L2). |
| S-m1 / Q-m4 probe set differs from seal set | **Fixed.** The seal takes `expected` and refuses `recovery_in_progress` on any other started v8 attempt. `started_v8_attempts` filters by `work_id`. Mutation M4 fails `test_the_seal_refuses_attempts_that_were_not_probed`. |
| S-m2 / Q-m1 prepare races a lead change | **Fixed.** `create_attempt` runs under `delivery_authority_guard`; `test_prepare_refuses_a_claim_that_changed_before_the_attempt_was_created`. |
| S-m3 / Q-m2 exceptions escape the return shape | **Fixed.** `LookupError`, `TypeError`, `ValueError`, and `ContractError` map to `lead_guard_ledger_unreadable`. |
| S-m4 missing or symlinked ledger read as empty | **Fixed.** A symlink, or a missing ledger with attempt directories, refuses. `test_a_lost_or_symlinked_ledger_is_never_read_as_empty`. |
| S-m5 unbounded legacy receipt hashing | **Fixed by removal.** A pre-column v8 predecessor has no digest, so its link fails validation (fail-closed). |
| Q-m3 / S-n1 / S-n2 manager grants and ledger-level fence | **Fixed.** The seal bumps `owner_generation`, so `consume_grant`, `consume_manager_grant`, and `prepare_verifier_send` refuse at the ledger. Allowed manager grants are fenced, not released. The dispatch-evidence check is declined: `allowed` implies no dispatch event, since `consume_grant` and `prepare_verifier_send` set `started` atomically. |
| Q-m5 test gaps | **Partly fixed.** Added a `started` action trigger and an altered-generation link case. **Accepted residual:** no dedicated test for an `unknown` manager call as the trigger (the same `_unresolved_action` query covers `manager_calls`), or for `_v8_limit_reason`'s lineage count on the recovery regrant path. |
| Nit: predecessor paid excludes `not_dispatched` | **Fixed** with a comment. |
| Nit: relative receipt path in the fallback | **Moot**; the fallback was removed. |
| Nit: the writable open runs DDL after the probe | **Accepted:** idempotent. |
| S-n3 `send_lock` lacks `O_NOFOLLOW` | **Declined here**; a carried follow-up that predates 1b. |
| ADR: v7 `unknown` now blocks a lead change | **Fixed** in ADR 0016. |
