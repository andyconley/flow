# Brief: adversarial review of the chunk 2 definition

Run `chartered-delivery-recovery-2`, lane `define`. Read-only: do not edit files. Return findings inline; the orchestrator records them.

## Task

Challenge the draft `requirements.md` and `acceptance-criteria.md` for chunk 2 of chartered v8 delivery recovery, from your role's accountable perspective (below). The parent's requirements were approved on 2026-09-23. Chunk 2 was only outlined there, so the new surfaces are the real subject: the v8 `resolve-execution` route, manager-call resolution, operator response import, resolution binding, the v8 no-dispatch regrant, and observation-backed reconcile. The draft adds three findings from reading the code today. Test them.

## Evidence inventory (exists now; worktree `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`, branch `codex/chartered-delivery-recovery-2` = 1b at `8c79953`)

- **Already exists:**
  - Draft: `.flow/runs/chartered-delivery-recovery-2/requirements.md`, `acceptance-criteria.md`.
  - Parent intent: `.flow/runs/chartered-delivery-recovery/requirements.md` (requirement 4; non-goals line 90), `acceptance-criteria.md` (AC4 chunk 2, AC5, AC8, AC10, AC12), `solution.md` (item 11; chunks at lines 118-138; risks R3, R5 at 143-145), `research/plan-architecture.md` §5 (lines 486-513: chunk 2 components, R5 gaps 1-4).
  - ADRs: `docs/adr/0016-chartered-v8-recovery.md`; ADR 0012 in `docs/adr/`.
  - 1b archive: `.flow/runs/chartered-delivery-recovery-1b/archive.md` (follow-ups, residuals L1, S3, S4).
  - Code:
    - `cli/execution_gateway.py:900-` `resolve_attempt` (v8 refusal at 911-913; attempt-local evidence preservation), `:602` `inspect_attempt`;
    - `cli/execution_ledger.py:101` `recovery_resolutions` (references `actions`), `:1248-1307` `resolve_unknown` (completed needs a `response_observations` row; not_dispatched needs status `allowed`), `:1309-1330` `regrant_not_dispatched` (hardcoded 6/3 caps), `:923` `observe_manager_response` (accepts `started`/`unknown` → `completed`), `:1188` `observe_response`, `:624` `_unresolved_action`, `:213` `send_lock`, `:434` `claim_recovery`;
    - `cli/delivery_gateway.py:930` `recover_delivery` (v5 evidence-import precedent; v6-v8 routed to `_resume_chartered`), `:832` `resume_delivery`;
    - `cli/delivery_recovery.py` (eligibility, `reconciliation_required` blockers), `cli/delivery_projection.py:68` (inspection).
  - Tests with a hardcoded MAF path: `tests/test_maf_continuation_supervisor.py:16`, `tests/test_maf_recovery.py:230,260,301`, `tests/test_maf_post_resolution_continuation.py:39`.
- **Partially covered:** resolution evidence preservation (`resolve_attempt`, v5 only); resolution replay idempotence (`resolve_unknown`, actions only).
- **Checked and absent:** a manager-call resolution record; any v8 route through `resolve-execution`; an operator response import path for v8; a generation-chain binding check on resolutions.
- **How searched:** grep for `recovery_resolutions`, `resolve_unknown`, `regrant_not_dispatched`, `observe_*`, `v8_resolution_requires_chunk_2` across `cli/`; reads of the anchors above.

## Output

1. Findings ranked critical, important, or suggestion. Each has a concrete scenario, the requirement or AC it hits, a claim status (observed, inferred, or unverified), and a proposed disposition from: requirement changed, AC changed, non-goal clarified, assumption confirmed or rejected, open question recorded, next lane changed, or deferred.
2. Your answer to each open question Q1–Q3 from your perspective, or "not my call" with why.
3. Is the draft ready for approval after your dispositions? Should the next lane be `flow-solution` or `flow-plan`?

Keep it under ~700 words.
