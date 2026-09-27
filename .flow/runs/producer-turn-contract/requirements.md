# Requirements: producer-turn-contract

Compact definition written from the `/flow-plan` engagement on 2026-09-26. The engineer approved: 1a, 2a, 3 yes, 4 as recommended, 5 yes.

## Problem

Two Flow defects ended `v8-live-validation-2` attempt 2 (see `.flow/runs/v8-live-validation-2/validation-results.md`).

- **D7: the manager isn't told the producer's one-call contract.** In a chartered job, the approved editor (the producer) gets exactly one call per attempt. The ledger refuses any later producer call with `producer_already_completed` (`cli/execution_ledger.py`), and Flow checks the worktree after that call. The facts Flow appends to the manager's task (`cli/delivery_gateway.py`, "Flow-verified execution facts") never say this. The live manager delegated "report back … do not edit any files yet". That spent the only producer call, and the edit check failed the attempt. The read-only specialists can't read files, so the manager has no way to inspect the code first. The editor's single turn is the only place inspection can happen.
- **D6: a misleading failure reason.** In `_verify_chartered_edit`, an empty change list falls into the scope branch and is reported as "editor changed files outside the approved job scope". The editor actually changed nothing.

## Users

Andy, Flow's only operator, who reads the failure reasons and decides expansions. The Claude delivery manager is the consumer of the new guidance.

## Outcome

- Every chartered job's manager is told, in Flow-supplied facts, that the editor gets one call and that the call must do the reading and the complete edit together.
- A no-edit outcome is reported as exactly that.

## Scope

- One new line in the chartered facts block (1a: Flow facts only, not charters).
- Distinct chartered edit-check failure reasons. Both no-edit paths say the editor made no edit: a clean worktree, and a declared-regression worktree whose allowed paths still match the baseline.
- Tests and a mutation check.
- One doc sentence.

## Non-goals

- Enforcement beyond guidance (2a): no decision-time warning, no classification of delegated task text. The existing fail-closed edit check stays the backstop.
- Charter or template changes.
- Changes to the non-chartered (legacy) facts line or to `_verify_edit`.
- Protocol version or receipt schema changes.
- Live or paid provider calls (4). Live proof belongs to `v8-live-validation-3`.

## Constraints

- All ledger limits and the edit check stay fail-closed.
- No backwards-compatibility work (sole user).
- Nothing is pushed or merged without the engineer asking.

## Assumptions

- The facts text isn't sealed into the charter or envelope; it's appended at runtime (the charter task is sealed separately, in `job_contract.task`). But each manager call's recorded `prompt_digest` covers messages that contain it. An attempt that's paused or interrupted before this change and resumed after it would fail replay, with "manager call ID reused with changed payload". Under no-backcompat that's acceptable. Before merging, confirm that no attempt is `expansion_paused` or interrupted.
- No code or test matches the exact old D6 strings. Verified by grep: only `cli/delivery_gateway.py:610` and `:612`.

## Risks

- The manager may still ignore the guidance. It is owned: the fail-closed check remains, and `v8-live-validation-3` measures it live.

## Open questions

None.
