# Adversarial Review: shaper-expansion-approval (definition)

- **Work item:** MAF adoption step 5, slice 1: expansion request and decision, with delegated Shaper headroom.
- **Reviewer roles:** product-manager (adversarial-product), business-analyst (adversarial-requirements; the expertise brief returned `no_match`), solution-architect (adversarial-architecture), security-reviewer (adversarial-security). All four were read-only and ran in parallel against `briefs/adversarial-review.md`.
- **Status:** dispositioned. Four items need an engineer decision (E1–E4).

## Evidence inventory

See `briefs/adversarial-review.md`. The orchestrator spot-checked these reviewer claims before dispositioning them:

- `decide_replan` accepts only protocols {2, 5, 6} (`cli/execution_ledger.py:816`).
- The runner hard-codes ceilings: `manager_call > 12`, `manager_round > 6`, `action_number > 6`, and `max_round_count=6` (`runtime/maf_runner/delivery_lead.py:175-256`).
- `_resume_chartered` resumes the same `attempt_id` (`cli/delivery_gateway.py:671-700`). Supersede creates a successor attempt.

## Findings and dispositions

### Architecture

- **SA1 (blocking), A2 rejected.** A denied row is permanent in its sequence slot. A re-proposal after resume carries a new checkpoint, so it gets a new `action_id` and the ledger raises. A replayed denial raises "needs reconciliation".
  - Disposition: requirement changed (R6). Resuming must not depend on Magentic re-proposing. Under the grant, Flow re-issues the saved denied proposal itself, as a Flow-owned pending action, and the denied row is marked superseded by the grant, never rewritten. The solution picks the mechanism.
- **SA2 (blocking), A1 rejected.** Recovery can't resume from a denial. A denied action has no bound checkpoint, and replan or manager-call denials seal the attempt as failed.
  - Disposition: requirement changed (R3). Add a new stop path, the expansion pause, distinct from interruption and failure, and a matching recovery mode. Mutation-check it (AC12).
- **SA3 (blocking), runner ceilings.** Grants above the runner's hard ceilings, or stock Magentic's 6-round limit, would be recorded but unusable.
  - Disposition: **E4**.
- **SA4 (major), replans can't be reached on v7 or v8.**
  - Disposition: **E1**.
- **SA5 (major), grant scope versus caps that count across the lineage.** This is the same issue as SEC3.
  - Disposition: **E3**.
- **SA6 (minor), A3 confirmed.** The caveat about the runner's round counter is covered by E4.
- **SA7 (minor), lead-claim state while waiting.**
  - Disposition: requirement changed (R3). While waiting, the claim stays `active` at the same generation. A decision and resume need that generation and never force a supersede.
- **SA8, ledger grants rather than charter amendment: confirmed.** The condition is that automatic approval reads headroom only from the sealed charter artifact, and the decide CLI takes the ADR 0016 locks.
  - Disposition: constraint added.

### Security

- **SEC1 (blocking), the manager controls the amount.**
  - Disposition: requirement changed (R2, R4). Flow computes the amount from the denying ledger row: exactly one unit. The rationale is display-only, never parsed, and escaped in output. AC added.
- **SEC2 (blocking), request identity and replay double-charging.**
  - Disposition: requirement changed (R2, R7). A request is keyed uniquely on the denied row (attempt, kind, row ID), and recording it is idempotent. Each grant is consumed by exactly one later allowed decision. A crash between request and approval draws headroom once (AC4, AC10).
- **SEC3 (major), headroom refilled per attempt.**
  - Disposition: **E3**.
- **SEC4 (major), manual verifier grants above 2.**
  - Disposition: AC changed. Any grant that would take effective verifier calls above 2 is refused, automatic or manual. `verifier_retry_denied` and `producer_already_completed` are listed as hard denials (AC3).
- **SEC5 (major), the pool could widen capabilities.**
  - Disposition: **E2**. If the pool stays, entries are validated against `prohibited_capabilities`, and a grant names exactly one role and digest.
- **SEC6 (major), the approver is a self-declared string.**
  - Disposition: requirement changed (R5). Deciding refuses unless the attempt is stopped: no started or unknown action or manager call, the recovery lock free, and no live supervisor child. Refusal in AC5, mutation in AC12. The approver string is recorded as a declaration, as in `resolve-execution`, for a single user.
- **SEC7 (minor), receipts should check authority, not just totals.**
  - Disposition: AC9 changed. The validator also rejects:
    - an automatic approval beyond the headroom left at that point in the order;
    - a grant under the wrong authority;
    - a grant larger than its request;
    - a grant tied to a different generation or attempt.
- **SEC8 (minor), atomic cancellation.**
  - Disposition: AC10 changed. Decide, supersede and release check request state in one `BEGIN IMMEDIATE`. A race leaves exactly one outcome.

### Requirements

- **BA1 (major), finding pending requests.**
  - Disposition: requirement changed (R3). `flow run status <work-id>` and `flow run list` show a pending expansion as the next action, and `inspect-delivery` shows the details. A cross-project inbox is a non-goal.
- **BA2 (blocking), re-proposal after a denial.**
  - Disposition: requirement changed (R6) and AC7. A denied request can't be decided again. If the manager later proposes the same kind of action again, that is a new request keyed on its own denied row. With no headroom change, it escalates again.
- **BA3 (minor), "headroom remaining" was undefined.**
  - Disposition: AC2. It reflects the automatic grants already recorded in the headroom scope (see E3).
- **BA4 (minor), the concurrent loser's outcome.**
  - Disposition: AC10. The second decision is refused with `expansion_already_decided` and nothing changes.

### Product

- **PM1 (minor), no usage signal.**
  - Disposition: non-goal clarified. Receipts record every request and decision, so counts can be derived later. No metric in slice 1.
- **PM2 (minor), the pool broadens slice 1.**
  - Disposition: **E2**.
- **PM3 (minor), the charter non-goal was misleading.**
  - Disposition: non-goal clarified. The charter *shape* gains sealed headroom fields at `start-plan`, but a grant never re-seals or re-versions it.

## Engineer decisions needed

- **E1, replans.** Drop replan expansion from slice 1 (recommended; v8 replans are unreachable today), or fix v8 replans first as a prerequisite.
- **E2, the optional specialist pool.** Defer it to a later slice (recommended: the envelope roster is pinned at prepare, so adding a role mid-attempt is a new mechanism with its own security surface), or keep it in slice 1 with the SEC5 controls.
- **E3, the scope of headroom and grants.** Scope both headroom and grants to the delivery lineage, meaning the attempt plus any superseding attempts (recommended; it matches the existing caps that count across the lineage, and supersede can't refill headroom). The alternative is to keep them per attempt and exclude granted usage from a successor's count.
- **E4, runner ceilings.** Validate base + headroom + grants against the runner's hard ceilings, at sealing and at each decision (recommended for slice 1), or make the runner ceilings come from the envelope (larger).

## Approval impact

- **Requirement changes:** R2, R3, R4, R5, R6 and R7 as above, plus E1–E4.
- **Acceptance criteria changes:** AC2, AC3, AC4, AC5, AC7, AC9, AC10 and AC12 as above.
- **Non-goal changes:** usage metrics; the charter-shape wording; a cross-project inbox.
- **Assumption changes:** A1 and A2 rejected and replaced by requirements; A3 confirmed with the runner-ceiling caveat.
- **Next-lane impact:** `flow-solution`, starting with a resume-mechanics spike (SA1–SA3) before contract work.

## Engineer decisions (2026-09-25)

- **E1 (a):** replan expansion is dropped from slice 1.
- **E2 (a):** the optional specialist pool is deferred.
- **E3 (a):** headroom and grants are scoped to the delivery lineage. This revises D5 and D7.
- **E4 (a):** base + headroom + grants are validated against the runner ceilings at sealing and at each decision.

`requirements.md` and `acceptance-criteria.md` are revised to match.
