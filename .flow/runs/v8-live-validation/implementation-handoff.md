# Implementation Handoff: v8 live validation

- **Lane:** `flow-implement` (operational). Follow the runbook in `plan.md`, Phases A–C, in order.
- **Run branch:** `codex/v8-live-validation`, for run artifacts only.
- **Job branch:** `job/decide-expansion-docs`, in the worktree at `~/src/flow-v8-live-job`.

## Read first

1. `plan.md`: the runbook, the plan amendments and the contingencies.
2. `validation-plan.md`: the evidence required for each AC.
3. `acceptance-criteria.md` (AC8's five outcomes) and `requirements.md` (R4, R6, R7).

## Invariants

- **No Flow code changes.** A defect found live is recorded, and fixed in its own run.
- **Nothing is staged.** Don't prompt or alter the manager, producer or verifier beyond the approved job charter.
- **Andy decides every escalated request.** Present the request first, then act on his reply.
- **Paid calls need a go.** No paid call happens before Andy's go at the launch gate.
- **The worktree stays clean at its HEAD** until launch. The job commit contains only the test.
- **Evidence goes in the run folder.** Save it under `.flow/runs/v8-live-validation/evidence/`, as captured JSON and text.

## Known facts

- **Installed release:** v0.36.0 (updated 2026-09-26). The sealed digests match the installed specialists.
- **Prepare accepts the manifest, roster and charter** (architect review A6). The job charter is taken through `input_evidence` and isn't sealed, so its sha256 is recorded.
- **Runtime:** 600 seconds per launch. The Ollama verifier call is capped at 60 seconds, so warm the model first.
- **Expected path:** about 6 or more manager calls. Call 5 gets the automatic grant, and call 6 escalates. The resume is in answer mode from the verifier's checkpoint.
