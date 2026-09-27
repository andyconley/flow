# Adversarial Review Brief: v8-live-validation-3 (definition)

Review the draft definition, read-only, and challenge it from an architecture perspective. Return your findings with evidence (file:line) and a recommended disposition for each: requirement changed, acceptance criterion changed, non-goal clarified, assumption confirmed or rejected, or open question. Rank the findings Critical, Important or Suggestion.

## Under review
- `.flow/runs/v8-live-validation-3/requirements.md`
- `acceptance-criteria.md`
- `shaper-intent.json`
- `job-charter.json`
- `orchestration.json`

## Context
- **This is the third live run.** It is adapted from the archived `.flow/runs/v8-live-validation-2/` (read its `requirements.md`, `acceptance-criteria.md`, `validation-results.md` and `archive.md`). That run found D3–D7, and all of them are now fixed:
  - D3: `.flow/runs/ollama-verifier-think`;
  - D4 and D5: `.flow/runs/manager-progress-retry`, ADR 0018;
  - D6 and D7: `.flow/runs/producer-turn-contract`.
- **v0.38.0 adds cancel and abandon** (`.flow/runs/step5-cancellation`, ADR 0019). A stuck attempt can now be sealed `abandoned`, and a successor can run on the same work id.
- **Check the "Changes" list in `requirements.md`.** Is it complete and correct? Is anything from run 2 or from the fixes still missing?
- **Still unproven live:**
  - an automatic grant;
  - a manager-call replay across a resume;
  - a live verifier evaluation;
  - a completed job.

## Evidence inventory (what exists; check before claiming absence)
- **Prepare:** `cli/delivery_gateway.py` `prepare_chartered_delivery`. It checks the roster digests, the base delegations against the roster, the worktree baseline and project `.flow` identity, and the predecessor listing for a successor.
- **Lineage and grants:**
  - `cli/execution_ledger.py`: `_v8_lineage_locked`, the lineage count queries, `_expand_locked`, `decide_expansion`, `seal_terminal_uncertain`;
  - ADR 0017: grant scope E6a, where paid and verifier calls are lineage-scoped;
  - ADR 0019.
- **The D7 facts text:** `_execution_facts` in `cli/delivery_gateway.py`, and `.flow/runs/producer-turn-contract/`.
- **D4 manager retries:** `runtime/maf_runner/` and ADR 0018. A retried progress reply counts as a manager call but not as a round.
- **Runner ceilings:** `runtime/maf_runner/limits.py`.
- **Intent validation:** `cli/delivery_contracts.py` `validate_shaper_intent`, `validate_expansion_headroom`.
- **Abandon and stuck:** `cli/delivery_termination.py`.
- **Job worktree:** `~/src/flow-v8-live-job-2` at `d6d771f2`, which is clean. The job charter is byte-identical to run 2's.

## Focus
- **Expansion events.** Given Magentic's call pattern and the D4 retry accounting, do the limits and headroom still produce both an automatic grant and an escalation?
- **Change 5 (paid-call headroom for a successor).** Is it right? Does lineage accounting actually block a successor's second edit under a base of 1 with no headroom, and does `paid_worker_calls` headroom of 1 fix it? Does `validate_expansion_headroom` or `limits.py` allow it?
- **Anything that would make `approve-definition`, `start-plan` or prepare refuse.** For example, `shaper-intent.json` changes, the reused worktree, or the successor preconditions.
- **The acceptance criteria.** Are the new or changed ones (AC2, AC8, AC10, AC12, AC13) observable and unambiguous?
