# Implementation Handoff: v8 live validation 2

- **Lane:** `flow-implement`, operational. Follow `plan.md`, Phases A–C, in order.
- **Run branch:** `codex/v8-live-validation-2`, for run artifacts only.
- **Job branch:** `job/decide-expansion-docs-2`, in the worktree at `~/src/flow-v8-live-job-2`.

## Read first

1. `plan.md`: the runbook, the binding amendments (especially "an uncertain send ends this run's attempts") and the contingencies.
2. `validation-plan.md`: the evidence required for each AC.
3. `acceptance-criteria.md` (AC8's outcomes, and AC12) and `requirements.md` (the six changes from the first run).

## Invariants

- **No Flow code changes.** A defect found live is recorded, and fixed in its own run.
- **Nothing is staged.** Don't prompt or change the manager, producer or verifier beyond the approved job charter.
- **Andy decides every escalated request.** Present the request first, then act on his reply.
- **Paid calls need a go.** No paid call happens before Andy's go at the launch gate. The verifier gate is local and free.
- **The worktree stays clean at its HEAD** until launch. The job commit contains only the test.
- **Evidence goes in the run folder,** under `.flow/runs/v8-live-validation-2/evidence/`. It must never include symlinks.

## Known facts

- **Installed:** v0.36.1 (2026-09-26). The sealed digests match the installed specialists.
- **Fixed caps in code:** manager 120 s, producer 300 s, verifier 60 s. Any of these firing means an uncertain send and the end of the attempts. The 600 s launch deadline can be resumed.
- **First-run timings:** manager calls took 21.0, 9.2 and 12.2 s. The producer turn was cut off by D1 at 94.2 s.
- **Expected path:** about 6 manager calls. Call 5 gets the automatic grant and call 6 escalates. The resume is in answer mode from the verifier's checkpoint.
- **Scripts:** `scripts/ledger_timings.py` (read-only per-call timings, checked against the first run's ledger and a synthetic verifier case) and `scripts/verifier_gate.py` (the timed go/no-go check, built the way Flow builds its verifier call).
