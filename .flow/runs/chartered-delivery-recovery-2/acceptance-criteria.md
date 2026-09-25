# Acceptance Criteria: chunk 2

Status: **approved by the engineer on 2026-09-24** (revised after adversarial review). Parent numbering is kept where a criterion comes from the parent.

**Operator sequence used by every boundary test:**
1. `flow run recover-delivery-lead` is refused with `reconciliation_required`, and names the blockers.
2. `flow run resolve-execution` records the resolution.
3. `flow run recover-delivery-lead` continues.

1. **AC4 (a), (c), (e): kill-boundary matrix.** Each boundary has a deterministic test that kills the attempt and runs the operator sequence against Flow-owned evidence. It asserts the terminal state, the exact ordered provider sends, and the receipt.
   - (a) a manager call is `started` or `unknown` with a Flow-owned response;
   - (c) a producer send was claimed, and its response is durably observed or captured in a Flow trace;
   - (e) a verifier send was claimed, and its response is durably observed. The resolved response is evaluated under the v8 contract.

   For (c) and (e) there is also a variant with no Flow-owned response. It stays refused, and `inspect-delivery` reports that it is unresolvable and can only be abandoned.
2. **AC5: resolution binding.** Recovery stays refused until a resolution matches the item kind and id, the attempt, and a generation in the recovery chain. Each of these subtests stays refused:
   - a resolution for another action or manager call;
   - a resolution for another attempt, built with an injected ledger row;
   - a resolution at a generation outside the chain.

   After `resolved_completed`, recovery continues with zero resends.
3. **v8 resolution route.** `resolve-execution` on a v8 attempt refuses in each of these cases, with a stable reason and no mutation, shown by a snapshot comparison of the ledger and claim files:
   - a terminal attempt;
   - a live run (`attempt_running`);
   - a stale expected generation;
   - an item that is not unresolved;
   - insufficient evidence (no Flow-owned response);
   - evidence that fails validation against the envelope.

   Two concurrent resolutions of one item yield exactly one. A `started` row, killed with no live run, is resolvable. The recovery chain stays continuous: a later recovery records no spurious interruption, and the receipt validates. v5–v7 resolution tests are unchanged and pass.
4. **Manager-call resolution.**
   - A manager call resolves into its own append-only record. Replaying the same content is idempotent, and a conflicting replay is refused.
   - A kill between observing the call and recording the resolution leaves the call neither completed nor unblocked.
5. **Observation-backed reconcile.** An action with a durable Flow-observed response but an interrupted completion is reconciled with zero resends, by the mechanism `flow-solution` chooses.
6. **v8 no-dispatch guard.** `regrant_not_dispatched` on a v8 attempt refuses with a stable reason and mutates nothing. The v5 no-dispatch regrant tests are unchanged.
7. **Lead change after resolution (1b E2).** In the AC9.3 fixture, once each uncertain row is resolved, a lead `resume` or `supersede` succeeds and seals the attempt as in 1b. An `unknown` manager call alone blocks the lead change.
8. **AC10: truthful receipt.** Receipt validation rejects an added resolution and a removed resolution, for both an action and a manager call, each in a separate subtest. A completed v7 receipt still validates unchanged.
9. **Inspection.**
   - A `reconciliation_required` refusal lists the blockers and points to `inspect-delivery`.
   - For each blocker, `inspect-delivery` names the applicable route and the evidence it needs, or states "unresolvable; abandon only".
   - It lists the resolutions relied on.
10. **Hardening.**
    - A test shows that `send_lock` refuses a symlinked lock path.
    - No test file hardcodes the MAF interpreter path. Every MAF-gated test reads `FLOW_MAF_PYTHON`.
11. **AC12: suite and mutation checks.** The full suite passes with 0 skipped, and the MAF-gated tests run locally. Each of these mutation checks makes its named assertion fail:
    - remove the resolution-binding check: AC5 fails;
    - a resolved-completed recovery resends: the worker-adapter-calls-equal-zero assertion for (c) and (e) fails;
    - remove the v8 no-dispatch guard: AC6 fails.
