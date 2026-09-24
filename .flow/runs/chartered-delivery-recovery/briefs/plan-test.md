# Brief: validation plan (test-engineer)

Run `chartered-delivery-recovery`, lane `plan`. The work is read-only except for the output file. Base: `main` at `9436527`, which has protocol v8 merged.

## Task

Produce the validation plan for chunk 1 in detail, and for chunk 2 in outline.

1. **Map every chunk-1 acceptance criterion to named tests.** The chunk-1 criteria are AC1, AC2, AC3, AC4 (b, d, f, g, h, i, and transport loss), AC6, AC7, AC8, AC9, AC10 (generation and marker), AC11, and the AC12 test-runner mutation. For each test give:
   - the target test file (existing or new) and a proposed test name;
   - the fixture approach;
   - the exact assertions: the terminal state, the ordered provider sends, the receipt fields, and the adapter and runner call counts.
2. **Design the kill-boundary harness.** Say how each boundary is reached deterministically:
   - reuse the existing `_run_v8` helper;
   - use the `delivery_control.failure_point` precedent;
   - use the planned keyword-only `seal_hook(point)` seam at `after-runtime-outcome`, `after-receipt-draft`, and `before-finish-attempt`.

   There must be no sleeps and no real providers.
3. **Specify the two mutation checks.** For the AC12 test-runner mutation in chunk 1, name the guard to remove and the assertion that must fail. Do the same for the chunk-2 worker-adapter mutation, in outline.
4. **Plan the regression proof** that v5, v6, and v7 are unchanged. Name the existing suites, and add a before/after ledger snapshot comparison for AC1.
5. **Give the ordered validation commands.** Include `python3.12 -m unittest discover -s tests` and `git diff --check`.

## Evidence inventory (exists today)

- `.flow/runs/chartered-delivery-recovery/acceptance-criteria.md` (approved), `solution.md`, and `research/solution-options.md`.
- Tests:
  - `tests/test_chartered_delivery_gateway.py`, which has the `_run_v8` helper, v8 tamper subtests, and v7-compat tests;
  - `tests/test_structured_verifier_ledger.py`;
  - `tests/test_maf_recovery.py`, the v5 resume and recover tests;
  - `tests/test_execution_recovery.py`;
  - `tests/test_delivery_control.py`;
  - `tests/test_maf_continuation_supervisor.py`;
  - `tests/test_maf_post_resolution_continuation.py`.
- `cli/delivery_gateway.py`:
  - `resume_delivery` :567 and `recover_delivery` :658, both v5-only;
  - `_execute_prepared_delivery` :741.
- The v8 test output digest is non-deterministic because it includes timing, which is why AC6 uses an injected runner that returns a new digest on every call.
- The full suite is currently 1370 tests, all passing, under python3.12.

## Constraints

- Tests must be hermetic: no network, no live Ollama, Claude, or Codex.
- Mark each claim `observed`, `inferred`, `recommended`, or `unverified`.

## Output

Write `.flow/runs/chartered-delivery-recovery/research/plan-validation.md`. Return a summary of 10 lines or fewer, plus the path.
