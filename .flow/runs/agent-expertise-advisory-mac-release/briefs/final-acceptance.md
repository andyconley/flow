# Brief: final acceptance review (light), advisory expertise Mac release

Run `agent-expertise-advisory-mac-release`, lane `review`. Read-only; return findings inline.

## Task

This run shipped in v0.29.0 (`HANDOFF.md`) but never got a lifecycle acceptance pass. Two of its own reviews asked for changes before release:
- `research/acceptance-review.md`: REQUEST CHANGES (a tested coordinator path, and one Flow-owned helper).
- `research/handback-review.md`: the documentation handback was incomplete.

Decide whether the shipped result is acceptable against `acceptance-criteria.md`. The decision rests on three questions:
1. Were those requested changes dispositioned? See `research/reconciliation.md`.
2. Do the fixes exist in the code on `main` today?
3. Do the validation results cover the ACs?

## Evidence inventory

- **Intent:** `requirements.md`, `acceptance-criteria.md`, `plan.md`, `solution.md`, `validation-plan.md`.
- **Evidence:** `validation-results.md`, `HANDOFF.md`, and the files under `research/`: `acceptance-review.md`, `handback-review.md`, `privacy-review.md`, `rollout-review.md`, `reconciliation.md`, `test-strategy.md`.
- **Code on `main`:** `cli/render.py` (the coordinator guidance), `cli/expertise_commands.py` (or wherever `flow expertise brief` / `disposition` / `feedback` live; use grep), the command reference docs, and the tests matching `test_expertise*`.
- **Live-use signal (orchestrator-observed, 2026-09-24/25):** in another session, generated coordinators ran `flow expertise brief --task-stdin` and `disposition --handback-stdin` successfully. That produced `admitted`, `no_match`, and completed post-receipts.

## Output

A verdict (ready to accept, or needs refinement), each requested change marked resolved or unresolved with `file:line`, a per-AC status, and residual risks. Keep it under ~600 words.
