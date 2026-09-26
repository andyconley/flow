# Adversarial review brief: shaper-expansion-approval

## Task

Challenge the draft definition from your accountable role:

- `.flow/runs/shaper-expansion-approval/requirements.md`
- `.flow/runs/shaper-expansion-approval/acceptance-criteria.md`

This is **read-only**. Return findings to the orchestrator; do not edit files.

**Treat D1–D7 as settled by the engineer.** Challenge them only if a decision is internally contradictory or unsafe. Say which, and why.

Report each finding as:

- a severity: blocking, major or minor;
- the claim, with a status: observed, inferred or unverified;
- evidence: a path and line;
- a proposed disposition: requirement changed, acceptance criterion changed, non-goal clarified, assumption confirmed or rejected, open question, or next lane changed.

Keep it under about 600 words. Flow has one user, Andy, and backwards compatibility is not required.

## Evidence inventory

**Already exists:**

- **Contract validation.** `cli/delivery_contracts.py`:
  - `validate_shaper_intent` (around lines 100–160) forces `delegation_matrix == {max_delegations, delegated_expansion: false}` and checks the budget envelope.
  - `build_delivery_charter` (around lines 183–225) seals `limits`, `eligible_specialists` and `escalation_stop_cancellation: {scope_expansion: "halt_for_shaper", cancellation: "Flow_only"}`.
- **Denials.** `cli/execution_ledger.py`:
  - `decide` (around lines 660–800) produces `delegation_cap`, `paid_call_cap`, `verifier_call_cap`, `verifier_retry_denied`, `concurrency_cap`, `specialist_denied`, `provider_denied`;
  - `decide_replan` (around 803–850) produces `replan_cap`;
  - the manager call gate (around 860–910) produces `manager_call_cap`, `manager_round_cap`.
- **Gateway.** `cli/delivery_gateway.py`:
  - chartered prepare checks the roster against the sealed charter (around lines 290–440, the "runtime roster expands the sealed Delivery Charter" check);
  - a denied specialist call returns `{"status": "denied", ...}` to Magentic (around line 1401);
  - resume and recovery run through `recover_delivery_lead`, `resolve_execution` and `inspect_delivery`.
- **Recovery.** `cli/delivery_recovery.py`: v8 recovery reasons, the recovery chain, and `unbound_resolutions`.
- **Lead claim.** `cli/delivery_control.py`: generation fencing and the `active`, `attention_required` and `released` statuses.
- **ADRs:**
  - `docs/adr/0014-shaper-delivery-ownership.md`: sealing at `start-plan`, the generation-fenced claim, and explicit resume or supersede;
  - `docs/adr/0015-flow-owned-structured-verifier-evaluation.md`: the verifier cap of 1–2;
  - `docs/adr/0016-chartered-v8-recovery.md`: lock order, and recovery from the latest bound checkpoint;
  - `docs/adr/0012-flow-owned-maf-recovery.md`: Flow-owned evidence only.
- **Design.** `docs/maf-adoption-design.md`, step 5, and the status table at the top.

**Partially covered:**

- The `halt_for_shaper` label exists, but no code acts on it.
- A deliberate stop at a denial has no route today. Recovery handles interruptions, not intentional pauses.

**Checked and genuinely absent:**

- Any expansion request or decision record, table, or CLI command.
- Any headroom field in the intent, contract or charter.
- Any grant-adjusted effective limit in the ledger or receipts.

**How this was searched:** grep for `expansion`, `halt_for_shaper`, `delegated_expansion` and `_cap"` across `cli/` and `runtime/maf_runner/`, plus reading the functions above.

## Role focus

- **product-manager:** Is slice 1 the right cut, worth doing before any live run? Is the scope too broad? Are the non-goals honest?
- **business-analyst:** Are the operator workflow and edge cases clear enough to test? Examples: several pending requests, a request while another is pending, repeated escalations, a denied request being re-proposed. Is each AC testable and unambiguous?
- **solution-architect:** Are the boundaries sound? Are A1–A3 plausible? Does anything conflict with ADRs 0012, 0014 or 0016? Should grants live in the ledger, or amend the charter?
- **security-reviewer:** Can a manager or provider output forge, inflate or replay a request or a grant? Can headroom be over-spent through concurrency or replay? Is anything granted by content Flow did not author?
