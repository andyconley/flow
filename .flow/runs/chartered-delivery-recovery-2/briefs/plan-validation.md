# Brief: validation plan, chunk 2 (test-engineer)

Run `chartered-delivery-recovery-2`, lane `plan`. Read-only; return the validation plan inline and the orchestrator records it in `validation-plan.md`.

## Task

For each acceptance criterion as amended (see `acceptance-criteria.md` plus the "Amendments from flow-solution" section of `requirements.md`), name the test or tests that prove it. For each test give its class, fixture, the kill point or seam, and the exact assertions, including the before-and-after snapshot for refusals and the ordered provider-send list. Reuse existing fixtures (`RecoveryHarness`, `_kill_once`, `LeadChangeFenceTests._authority`, `CharteredFixture._run_v8`) where you can.

## Settled decisions

- v8 `resolve-execution`:
  - requires `--expected-generation`;
  - refuses `--evidence-file`, `resolved_not_dispatched`, and `still_unknown`;
  - resolves only from a stored `response_observations` row, at the current generation.
- Manager calls are abandon-only.
- The worktree guard and the no-dispatch guard are v8 only.
- The hardening covers `send_lock` O_NOFOLLOW and `FLOW_MAF_PYTHON`.

## Must cover

- **Boundaries (c) and (e):** a kill between `observe_response` (`cli/delivery_gateway.py:1353`) and `complete` (`:1358`) leaves the row `started`. A second variant has `complete` raise, so the row becomes `unknown`. Each is then refused, resolved, and recovered with zero resends. There is also a no-observation variant, which stays refused and is reported "abandon only".
- **Boundary (a):** a manager call is `started`/`unknown` and is abandon-only.
- **AC5 binding subtests:** a resolution for another action, for another attempt (an injected ledger row), and outside the chain generation.
- **Route refusals with no mutation:** each settled refusal, plus terminal, live (`attempt_running`), stale expected generation, not-unresolved, and no observation.
- **Concurrency:** two concurrent resolves yield one.
- **Risk R1:** resolve, then recover, then seal, then validate the receipt.
- **Receipt tamper:** an added and a removed resolution.
- **Inspection text.**
- **Lead change after resolution,** and an `unknown` manager call alone blocking a lead change.
- **The guards,** the `send_lock` symlink refusal, and no hardcoded MAF path (a test that greps the test tree is acceptable).
- **Mutations:** remove the binding check; resend on resolved-completed (worker-adapter calls equal zero for (c) and (e)); remove the v8 no-dispatch guard; resolve at a bumped generation (R1).
- **Commands:** the full suite with `python3.12`, 0 skipped, and the MAF-gated tests with `FLOW_MAF_PYTHON`.

## Evidence inventory

- `.flow/runs/chartered-delivery-recovery-2/acceptance-criteria.md`, `requirements.md`, `solution.md`, `research/solution-verify.md`.
- The 1b validation plan as a format precedent: `.flow/runs/chartered-delivery-recovery-1b/validation-plan.md`.
- `tests/test_chartered_delivery_recovery.py`, `tests/test_chartered_delivery_gateway.py`.

Keep it under ~1000 words.
