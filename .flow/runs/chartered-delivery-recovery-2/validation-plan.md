# Validation Plan: chunk 2

Drafted by `plan-validation` (test-engineer; request `5027f60f…`, `no_match`) and reconciled with `plan.md`. Numbering follows `acceptance-criteria.md` (AC1–AC12 for this run; AC4 removed). Tests live in `tests/test_chartered_delivery_recovery.py` unless noted. They reuse:

- `RecoveryHarness`, `_kill_once`, `_killed`, `_recover`, `_assert_recovered_receipt` (which gains a `resolutions=` parameter);
- `CharteredFixture._run_v8` and `.prepare`;
- `CharteredRecoveryRefusalTests._state` and `._assert_refused_without_mutation`;
- `LeadChangeFenceTests._authority`.

Refusal reasons are asserted against the named constants in `cli/delivery_recovery.py`, not string literals.

## AC map

| AC | Tests |
|---|---|
| **AC1 (c)/(e): observed and `started`** | `test_boundary_c_or_e_started_with_stored_response_resolves_and_recovers`, with `subTest(role=producer\|verifier)`. `_kill_once("complete")` kills after `observe_response`. The steps: the row is `started` and has a `response_observations` row; recovery is refused `reconciliation_required` with no mutation, and the detail points to `inspect-delivery`; resolve with `expected_generation` set to the current generation; the row is now `completed/operator_resolved_completed`; recover. Assert `sends` gained no entry and `test_calls` did not rerun. The receipt validates with one resolution and one interruption at generation 1, and a verifier is evaluated with no resend. |
| **AC1 (c)/(e): observed and `unknown`** | `test_boundary_c_or_e_unknown_when_complete_raises_resolves_and_recovers`. Patch `ExecutionLedger.complete` to raise after `observe_response`, which drives `mark_unknown` (`delivery_gateway.py:1369-1372`). The row is `unknown`. Then the same resolve, recover, and zero-resend assertions as above. |
| **AC1 (c)/(e): no observation** | `test_boundary_c_or_e_with_no_stored_response_is_abandon_only`. `_kill_once("observe_response")`. Resolve refuses `evidence_insufficient` with the state unchanged. Inspection says "unresolvable; abandon only". Recovery is still refused. |
| **AC1 (a)** | `test_boundary_a_manager_call_is_abandon_only`, with `subTest(status=started\|unknown)`. Resolve refuses `unresolvable_abandon_only` with no mutation. Inspection says abandon only. `release` succeeds. |
| **AC2: binding** | `test_resolution_binding_rejects_wrong_action_wrong_attempt_and_wrong_generation`. Three injected-row subtests: another action, another attempt, and a generation outside the chain. Each is refused `resolution_unbound` (or stays `reconciliation_required`) with the state unchanged. A correct resolution then recovers with zero resends. |
| **AC3: route refusals** | `test_v8_resolve_execution_refuses_each_case_without_mutation`, with one subtest per reason: `v8_evidence_file_refused`, `expected_generation_required`, `v8_disposition_unsupported` (for `resolved_not_dispatched` and `still_unknown`), `attempt_terminal`, `attempt_running` (a live `recovery_lock`), `owner_generation_stale`, `item_not_unresolved`, `evidence_insufficient`, and `evidence_invalid` (a tampered observation digest). Each compares `_state` before and after. |
| **AC3: concurrency** | `test_two_concurrent_resolutions_yield_exactly_one`: exactly one resolution row. The loser gets `recovery_in_progress` or an idempotent replay. |
| **AC3: v5–v7 CLI** | `test_v5_to_v7_resolve_execution_is_unchanged`: a missing `--evidence-file` gives `evidence_file_required`, `--expected-generation` gives `expected_generation_v8_only`, and the existing v5–v7 resolve tests pass unmodified. |
| **AC3: R1 chain** | `test_resolve_then_recover_then_seal_keeps_the_chain_continuous`: there is no spurious interruption from resolve, and `validate_receipt` passes. |
| **AC3: ledger** | Unit tests for `resolve_observed_v8`: each refusal, an idempotent replay, a conflicting replay, and `_append_resolution_locked` keeping `resolve_unknown`'s v5 behavior byte-identical. |
| **AC3: entry points** | Extend `CharteredRecoveryEntryTests`: `_resolve_chartered` is reachable only from `resolve_execution`, and `resolve_execution` only from `flow.main`. |
| **AC6: no-dispatch guard** | `test_v8_no_dispatch_regrant_is_refused_without_mutation`. The v5 regrant tests are unchanged. |
| **AC7: lead change** | `test_lead_resume_or_supersede_succeeds_once_every_uncertain_row_is_resolved` (the `_uncertain_verifier_send` fixture with an observation variant, then `_assert_seals`), and `test_an_unknown_manager_call_alone_blocks_a_lead_change` (a manager adapter raises, then `_authority` is compared before and after). |
| **AC8: receipt** | `test_receipt_rejects_an_added_resolution` and `test_receipt_rejects_a_removed_resolution`, starting from a boundary (c) receipt. A completed v7 receipt still validates. |
| **AC9: inspection** | `test_inspect_delivery_guides_each_blocker`: the route text for the observed case, abandon only for the unobserved and manager cases, the listed resolutions, the owner generation in the text output, and the refusal pointer. Update the existing expectation at `:1106`. |
| **AC10: hardening** | `test_send_lock_refuses_a_symlinked_lock_path` (the target is unchanged). `test_no_test_file_hardcodes_the_maf_interpreter_path` (a static scan of `tests/` for `/private/tmp/flow-maf`; each MAF module imports `tests/maf_env.py`). |
| **AC12: worktree guard** | `test_v8_prepare_refuses_a_worktree_containing_project_flow` (commit 4): worktree set to the root refuses `worktree_contains_project_flow`, and no attempt directory or ledger row is created. `test_v8_resolve_refuses_an_envelope_worktree_containing_project_flow` (commit 10): the route refuses on `envelope["worktree"]` with no mutation. |

## Mutation checks (AC11)

Break one guard, confirm the named test fails, then restore the source from a byte copy (the tree may hold uncommitted work):

- **M1.** Delete `unbound_resolutions`: the AC2 binding subtests fail.
- **M2.** Make `_completed_reply` resend: the zero-sends assertions for (c) and (e) fail.
- **M3.** Drop the v8 no-dispatch guard: AC6 fails.
- **M4.** Resolve at a bumped generation: the R1 chain test fails.

## Commands

- `python3.12 -m unittest discover -s tests` with `FLOW_MAF_PYTHON` set: the full suite, **0 skipped** (the baseline at 1b is 1443).
- The MAF-gated modules alone, with `FLOW_MAF_PYTHON` set: 0 skipped.
- `git diff --check`.
- Hermetic only; no live providers.
