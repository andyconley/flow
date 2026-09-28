# Implementation Handoff: v8 live validation 3

- **Lane:** `flow-implement`, operational. Follow `plan.md`, Phases A–C, in order.
- **Run branch:** `codex/v8-live-validation-3`, for run artifacts only.
- **Job branch:** `job/decide-expansion-docs-2`, in `~/src/flow-v8-live-job-2` at `d6d771f2`.

## Read first

1. `plan.md`: the runbook, the binding amendments (abandon, then successor, and the verifier precondition), and the contingencies.
2. `validation-plan.md`.
3. `acceptance-criteria.md` (AC8, AC10, AC12, AC13) and `requirements.md` (Changes 1–7).

## Invariants

- **No Flow code changes.** A live defect is recorded, and fixed in its own run.
- **Nothing is staged.** No prompting beyond the approved job charter, and cancel is used only for operational stops.
- **Andy decides every escalated request.**
- **Paid calls need Andy's go** at the launch gate, and a successor gets its own go.
- **The worktree is clean at `d6d771f2`** before each launch.
- **Evidence** goes under `.flow/runs/v8-live-validation-3/evidence/`, with no symlinks.
- **Stuck or stopped attempts** use the v0.38.0 CLI (`stuck`, `inspect-delivery`, `abandon-delivery`, `cancel-delivery`). Any Python step is a gap.

## Known facts

- **Installed:** v0.38.0, with the sealed digests matching.
- **Fixed caps in code:** manager 120 s, producer 300 s, verifier 60 s. Any of these firing is an uncertain send, which leads to abandon and possibly a successor. The 600 s launch deadline can be resumed.
- **Run 2 timings:** manager calls took about 9–21 s. A producer edit completed in attempt 1.
- **Expected path in attempt 1:** about 6 manager calls. Call 5 is the automatic grant and call 6 escalates, resuming in answer mode. D4 retries can move both earlier.
- **Expected path in a successor:** read it from the predecessor's `headroom_remaining` (plan, S2). Typically the edit is granted automatically from paid headroom, and manager call 5 escalates.
- **Generations:** decide, cancel and abandon take the ledger `.attempt.owner_generation`. `delivery-lead` takes the lead generation, `.delivery_authority.owner_generation`. Run every command from `~/src/flow`.
- **Scripts:** `scripts/ledger_timings.py` and `scripts/verifier_gate.py`, copied from run 2.
