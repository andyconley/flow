# Implementation Review: shaper-expansion-approval

- **Reviewers:** quality-reviewer and security-reviewer. Both were independent and read-only, and ran in parallel on commits `2b9e045`–`9ab48c5` on 2026-09-25. Each brief carried the full evidence inventory and the binding plan amendments.
- **Verdicts:**
  - Quality: request changes (1 major, 6 minor, 2 nits).
  - Security: 0 blocking, 0 major, 1 minor, 4 informational.
- **Fixes:** commit `31ac27b`. Each fix has a test, and Q1 and Q2 also have mutation checks (M9, M10).

## Quality findings

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| Q1 | major | A manager pause after a hard worker denial couldn't resume, because hard denials never bound their checkpoint. | **Fixed.** Every denied v8 worker proposal binds its checkpoint, and `bind_magentic_checkpoint` accepts any denied v8 worker row as a restore position. Test: `test_manager_pause_after_a_hard_worker_denial_resumes_in_answer_mode`. Mutation M9 caught. |
| Q2 | minor | A sealed attempt could keep a pending request or an unused grant. | **Fixed.** `_seal_attempt` closes open expansions for v8 before building the receipt, and the validator rejects any left open. Test: `test_a_failed_resume_seals_and_lapses_the_unused_grant`, `test_receipt_rejects_an_open_request_or_unused_grant`. Mutation M10 caught. |
| Q3 | minor | An unbound worker pause asked for a decision that could never resume. | **Fixed.** The link is checked before the decision status. |
| Q4 | minor | Lineage is bound at block level, and predecessor totals are self-reported. | **Fixed in part.** The validator now bounds predecessor headroom spending. Carrying lineage at block level is by design (an attempt has one lineage), and the seal-time comparison with the ledger is authoritative. Recorded in ADR 0017. |
| Q5 | minor | Headroom remaining isn't stored on the request. | **Accepted as a deviation.** AC2's "headroom remaining" is read live from `expansion_state` and inspect. Recorded in ADR 0017. |
| Q6 | minor | Two weak tests: the denial test accepted `failed`, and the untampered single-use case refused on row state. | **Fixed.** The denial test now asserts a sealed `failed` receipt with the denied request. In this fixture a denied retry can't reach a pass, so "can still finish" means the attempt seals a valid terminal receipt. The single-use test keeps both cases; the tampered case exercises the grant guard, which M5 proves. |
| Q7 | minor | An unrecoverable position after a decision named the wrong next step. | **Fixed.** It now reports `checkpoint_position_unrecoverable`. |
| nit | nit | The consistency rule compares base + headroom, not headroom alone (A11 wording). | **Accepted.** This is the sensible rule; recorded in ADR 0017. |
| nit | nit | A decide ceiling refusal is reachable only through unused grants. | **Recorded** in ADR 0017. |

## Security findings

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| S1 | minor | An expired send grant on an expansion-backed row made the attempt unsealable. | **Fixed.** The validator accepts a consumed grant whose row is `denied` with reason `grant_expired`, because the unit stays spent. `paused_expansion` ignores such rows, so ordinary recovery seals them. Test: `test_receipt_accepts_a_spent_unit_whose_send_grant_expired`. |
| S2 | info | The automatic ceiling check ignored units held by unused engineer grants (not reachable today). | **Fixed** as defence in depth. `_expand_locked` counts `_outstanding_units`, shared with `decide_expansion`. |
| S3 | info | A stale `decide` holder name can make a decide spin for 10 seconds before refusing. This differs from A10's "refuses". | **Accepted and recorded** in ADR 0017. The wait is bounded, and a `live` or `recovery` holder is still refused at once. |
| S4 | info | `runner_limits` values weren't checked at load. | **Fixed.** Each value must be a positive int, and the verifier ceiling must be 2 or less, or the import fails. |
| S5 | info | The standalone validator doesn't bind a request to its row's reason. | **Recorded** in ADR 0017: a receipt proves its expansion only together with `sealed_receipt_sha256`. |

## Verified sound (both reviewers)

- **Amount and authority:** the amount is always one unit per failing limit, computed by Flow. Hard predicates always win. Headroom is read only from the sealed charter projection.
- **Atomicity:** the request, the automatic grant and the allowed row commit in one transaction. Headroom counts every automatic grant across the lineage and is never refilled.
- **Single use:** a grant is consumed only by its own row, while available, under an active recovery, and a failed re-check rolls it back.
- **Races:** decide, supersede, release and recovery claim hold the ADR 0016 lock order, and each re-checks its preconditions inside `BEGIN IMMEDIATE`.
- **Supervisor guard:** relaxing it to the ceiling opens no send path; every call still goes through the ledger.
- **Output:** the rationale is escaped in text output and is never parsed.
- **Other protocols:** v5–v7 are unchanged.
