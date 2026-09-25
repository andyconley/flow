# Acceptance Criteria: chunk 2

Status: **approved by the engineer on 2026-09-24** (revised after adversarial review), and **amended with Option A** in `flow-solution` the same day (see "Amendments from flow-solution" in `requirements.md`).

Items are numbered **AC1–AC12 for this run**. A parent criterion is cited as "parent ACn" so the two numberings never collide.

**Operator sequence used by every resolvable boundary test:**
1. `flow run recover-delivery-lead` is refused with `reconciliation_required`. The refusal names the blockers and points to `inspect-delivery`.
2. `flow run inspect-delivery` shows each blocker's route and the owner generation.
3. `flow run resolve-execution <work> <attempt> <action> --disposition resolved_completed --expected-generation N --actor … --explanation …` records the resolution.
4. `flow run recover-delivery-lead` continues.

**Abandon-only path:** the existing, unchanged `release` (or the lifecycle `block`).

1. **AC1: kill-boundary matrix (parent AC4 (a), (c), (e); parent AC5).** Each boundary has a deterministic test that asserts the terminal state, the exact ordered provider sends, and the receipt.
   - **(c)** A producer send is left `started` (a kill between `observe_response` and `complete`), or `unknown` (`complete` raises), with a stored `response_observations` row. The operator sequence completes it with zero resends.
   - **(e)** The same for a verifier. The resolved response is evaluated under the v8 contract with no resend.
   - **(c)/(e) with no stored response.** Resolve refuses `evidence_insufficient` and mutates nothing. `inspect-delivery` reports "unresolvable; abandon only", and `release` succeeds.
   - **(a)** A manager call is `started` or `unknown`. Resolve refuses `unresolvable_abandon_only` and mutates nothing. `inspect-delivery` reports abandon only, and `release` succeeds.
2. **AC2: resolution binding (parent AC5).** Recovery stays refused unless each `operator_resolved_*` action has exactly one resolution matching its action id, the attempt, and a generation in the recovery chain. Each of these injected-row subtests stays refused, with the state unchanged:
   - a resolution for another action;
   - a resolution for another attempt;
   - a resolution at a generation outside the chain.
3. **AC3: v8 resolution route.** `resolve-execution` on a v8 attempt refuses in each of these cases, with its named reason and no mutation, shown by a snapshot comparison of the ledger and claim files:
   - `--evidence-file` given;
   - `--expected-generation` missing;
   - disposition `resolved_not_dispatched` or `still_unknown`;
   - a terminal attempt;
   - a live run (`attempt_running`);
   - a stale expected generation;
   - an item that is not unresolved;
   - no stored response;
   - a stored response that fails revalidation.

   Two concurrent resolutions of one item yield exactly one. A killed `started` row with no live run is resolvable. Resolve, then recover, then seal: no spurious interruption is recorded, and the receipt validates (risk R1). On v5–v7, a missing `--evidence-file` refuses `evidence_file_required`, `--expected-generation` refuses `expected_generation_v8_only`, and the existing resolution tests pass unmodified.
4. **AC4: removed.** Manager-call resolution was dropped with requirement 3; under C1 no Flow-owned manager reply survives. Manager calls are covered as abandon-only in AC1 (a).
5. **AC5: observation-backed reconcile.** Realized by AC1 (c)/(e) through the operator-confirmed route (Option A, Q3).
6. **AC6: v8 no-dispatch guard.** `regrant_not_dispatched` on a v8 attempt refuses `v8_no_dispatch_regrant_unsupported` and mutates nothing. The v5 no-dispatch regrant tests are unchanged.
7. **AC7: lead change after resolution (1b E2).** In the 1b fixture, once each uncertain action is resolved, a lead `resume` or `supersede` succeeds and seals the attempt as in 1b. An `unknown` manager call alone blocks the lead change, and nothing is mutated.
8. **AC8: truthful receipt (parent AC10, actions only).** Receipt validation rejects an added resolution and a removed resolution, each in a separate subtest, starting from a resolved-then-recovered receipt. A completed v7 receipt still validates unchanged.
9. **AC9: inspection.**
   - A `reconciliation_required` refusal lists the blockers and points to `inspect-delivery`.
   - For each blocker, `inspect-delivery` states "resolve-execution (stored response)" or "unresolvable; abandon only".
   - It lists the resolutions relied on, and shows the owner generation to pass as `--expected-generation`.
10. **AC10: hardening.**
    - `send_lock` refuses a symlinked lock path and leaves the target unchanged.
    - No test file hardcodes the MAF interpreter path; every MAF-gated test takes it from `FLOW_MAF_PYTHON`.
11. **AC11: suite and mutation checks (parent AC12).** The full suite passes with 0 skipped, and the MAF-gated tests run locally. Each of these mutation checks makes its named assertion fail:
    - **M1:** remove the binding check, and AC2 fails;
    - **M2:** a resolved-completed recovery resends, and the zero-sends assertions for AC1 (c)/(e) fail;
    - **M3:** remove the v8 no-dispatch guard, and AC6 fails;
    - **M4:** resolve at a bumped generation, and the AC3 R1 test fails.
12. **AC12: worktree guard.** Preparing a v8 chartered delivery with a worktree that contains the project's `.flow/` refuses `worktree_contains_project_flow`, and creates no attempt directory or ledger row. The v8 resolve route refuses on the envelope's worktree in the same way.
