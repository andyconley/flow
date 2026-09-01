# Test Current-State Analysis: Orchestration Safety Contract

## Scope and test boundary

The approved behavior is primarily deterministic, file-local validation: JSON manifest parsing, controlled values, relative-path containment, relationship checks, calculated risk, and stage-specific presence/identity checks. Those belong in unit tests. The public command and lifecycle gates cross process and on-disk boundaries, so they need subprocess integration tests using the existing temporary repository harness. The shared-external-mutation case can be proven with a local file fixture; it proves Flow's declarations and refusal paths, not arbitrary provider transaction semantics.

No current test needs network access for the new behavior. Release publication, the hosted GitHub release, and a release-install smoke remain manual/runtime evidence because they depend on the tagged artifact and CI credentials.

## Existing test architecture

- `tests/test_flow.py` is the project-wide `unittest` suite. It has no separate test package per CLI module.
- `FlowCliHarness` at `tests/test_flow.py:66` creates a temp repository with a `.git` directory, invokes `cli/flow.py` in a subprocess, and provides `setup_project`, fake HOME, and `assert_ok` helpers. This is the correct base for command, lifecycle, and persistence assertions.
- `load_cli_module` at `tests/test_flow.py:18` imports a CLI sibling while restoring `sys.path` and `sys.modules`. It is the correct helper for direct validator unit tests and avoids leaking bare module names between tests.
- Existing C-lite coverage is in `FlowCliTests`, especially `test_run_transition_refuses_invalid_gate_without_writing` (lines 355-369), `test_run_core_path_transitions_to_archive` (371-443), and `test_run_legacy_status_is_read_only_and_inferred` (445-459). The first already establishes the exact byte-for-byte `run.json`/`events.jsonl` refusal pattern this feature requires.
- Release-stage import coverage begins with `test_release_staging_requires_cli_siblings` (2302). Its exhaustive real sibling loop has an explicit expected module roster near line 2480; it must include `orchestration` after `cli/flow.py` imports it.

## Recommended test placement and helpers

Add an `OrchestrationValidationTests(unittest.TestCase)` class near the current C-lite tests in `tests/test_flow.py`, and an `OrchestrationCliTests(FlowCliHarness)` class immediately after it. Keeping direct tests independent of the subprocess suite makes finding-level assertions precise and keeps the expensive CLI paths focused on observable behavior.

### Suggested fixture helpers

Define these small test-only helpers close to the new classes:

- `_write_json(path, payload)`: creates parents and writes an indented JSON fixture.
- `_manifest(work_id="orchestration-demo", **overrides)`: returns a known-good minimally complete dispatch manifest. Every negative test changes one field from this baseline.
- `_write_run_artifact(repo, work_id, relative_path, content="evidence\\n")`: writes a required brief/evidence/output file under the run directory and returns its repo-relative POSIX path.
- `_orchestration_paths(repo, work_id)`: returns the manifest, `run.json`, and `events.jsonl` paths. Use it with an `assert_refused_unchanged` helper that snapshots `read_bytes()` before a gate attempt.
- `assert_findings(result, *rules)`: assert `ok == False`, finding rule/field identifiers, and corrective-action presence without asserting complete prose. JSON diagnostics should be decoded and asserted structurally.

The product validator should expose a pure entry point such as `validate_manifest(manifest_path, stage, repo_root)` returning a finding collection. `cmd_validate_orchestration` should only print that result. Unit tests then cover rules without stdout coupling; subprocess tests prove parser wiring, text, JSON, and exit code.

## Required unit tests: cli/orchestration.py

### Loading, schema, and diagnostics

1. `test_dispatch_accepts_minimal_standard_risk_manifest`
2. `test_dispatch_accepts_unknown_additive_object_fields`
3. `test_dispatch_rejects_invalid_json`
4. `test_dispatch_rejects_non_object_top_level_manifest`
5. `test_dispatch_rejects_missing_required_field`
6. `test_dispatch_rejects_work_id_that_differs_from_run_directory`
7. `test_dispatch_rejects_unknown_controlled_vocabulary_value`
8. `test_dispatch_rejects_absolute_or_parent_traversal_artifact_path`
9. `test_dispatch_rejects_missing_referenced_brief_or_evidence`
10. `test_findings_identify_field_subject_rule_and_corrective_action_without_artifact_contents`

Exercise unknown additive fields at nested objects as well as the top level if the contract promises additive forward compatibility there. Assert actual finding fields/rules, not JSON key ordering or exact English phrasing.

### Assignment, capability, output, and scope rules

1. `test_dispatch_accepts_every_required_capability_when_confirmed`
2. `test_dispatch_rejects_missing_required_capability`
3. `test_dispatch_rejects_unknown_required_capability_for_dispatch`
4. `test_dispatch_rejects_read_only_assignment_with_write_output`
5. `test_dispatch_accepts_output_inside_declared_write_scope`
6. `test_dispatch_rejects_output_outside_declared_write_scope`
7. `test_dispatch_rejects_duplicate_assignment_id`
8. `test_dispatch_rejects_missing_success_criteria`
9. `test_dispatch_rejects_missing_claim_status_expectation`
10. `test_dispatch_accepts_disjoint_concurrent_repository_scopes`
11. `test_dispatch_rejects_equal_concurrent_repository_scopes`
12. `test_dispatch_rejects_parent_child_concurrent_repository_scopes`
13. `test_dispatch_accepts_declared_serialization_for_overlapping_scopes`

Use path shapes such as `src/a.py`, `src/b.py`, and `src/` versus `src/a.py`. They prove lexical containment without platform-separator dependencies.

### Deterministic risk calculation

Parameterize every controlled hard trigger and test it returns `high`. Add separate boundary cases:

1. `test_risk_is_high_for_each_hard_trigger`
2. `test_risk_is_standard_with_no_triggers_or_aggravating_factors`
3. `test_risk_is_standard_with_one_aggravating_factor`
4. `test_risk_is_high_with_exactly_two_aggravating_factors`
5. `test_risk_is_high_with_more_than_two_aggravating_factors`
6. `test_rejects_stored_risk_classification_that_conflicts_with_calculation`

Use the approved enum list, not paraphrased values, so the tests catch accidental vocabulary drift.

### Shared-state and stage rules

1. `test_dispatch_rejects_same_target_structural_and_additive_concurrency`
2. `test_dispatch_accepts_same_target_structural_mutations_when_serialized`
3. `test_dispatch_accepts_distinct_external_targets`
4. `test_dispatch_reports_external_region_checks_as_declaration_level`
5. `test_handback_rejects_missing_declared_output`
6. `test_handback_rejects_missing_reconciliation`
7. `test_handback_rejects_missing_baseline_readback_comparison_or_execution_record`
8. `test_handback_rejects_destructive_mutation_without_exercised_recovery_or_irreversible_acknowledgment`
9. `test_handback_rejects_unexpected_delta_without_disposition`
10. `test_handback_accepts_local_external_mutation_record_with_readback_and_recovery_evidence`

The success fixture should capture a local target's initial hash, write the expected change, capture readback/comparison artifacts, restore it, and record the recovery result. A second fixture adds an unrecorded delta and must fail until its disposition artifact is referenced.

### Claims, reconciliation, and independent verification

1. `test_acceptance_accepts_each_material_claim_class`
2. `test_acceptance_rejects_unknown_claim_class`
3. `test_acceptance_rejects_observed_claim_without_evidence_reference`
4. `test_acceptance_rejects_inferred_claim_without_linked_observation`
5. `test_acceptance_requires_decision_owner_for_recommended_claim`
6. `test_acceptance_rejects_unverified_material_claim_promoted_to_accepted_fact`
7. `test_acceptance_rejects_unresolved_material_conflict`
8. `test_acceptance_accepts_resolved_conflicts_with_dispositions`
9. `test_acceptance_allows_standard_risk_without_distinct_verifier`
10. `test_acceptance_rejects_high_risk_when_verifier_matches_producer`
11. `test_acceptance_rejects_high_risk_when_verifier_matches_evidence_collector`
12. `test_acceptance_rejects_high_risk_without_verification_artifact`
13. `test_acceptance_accepts_high_risk_with_distinct_provider_identities`

Provider identity fixtures should cover human, agent, and external-provider forms with the same structural contract. Do not special-case provider labels.

## Required CLI and lifecycle integration tests

Place these in `OrchestrationCliTests(FlowCliHarness)` so they invoke the public `flow` command.

1. `test_validate_orchestration_text_success_and_failure`
2. `test_validate_orchestration_json_has_stable_envelope_and_exit_status` — require `ok`, `stage`, `manifest`, and `findings`; exit 0 only when `ok`.
3. `test_validate_orchestration_distinguishes_missing_run_from_missing_manifest`
4. `test_new_run_records_protocol_revision_two`
5. `test_existing_revision_one_run_transitions_without_orchestration_manifest`
6. `test_legacy_inferred_run_remains_read_only_and_verifiable` — extend the existing legacy test only if behavior remains clear.
7. `test_revision_two_definition_gate_refuses_missing_manifest_without_writing`
8. `test_revision_two_definition_gate_refuses_invalid_dispatch_manifest_without_writing`
9. `test_revision_two_plan_gate_refuses_invalid_dispatch_manifest_without_writing`
10. `test_revision_two_handback_gate_refuses_invalid_handback_manifest_without_writing`
11. `test_revision_two_acceptance_gate_refuses_invalid_acceptance_manifest_without_writing`
12. `test_complete_standard_risk_revision_two_lifecycle_reaches_archive`
13. `test_complete_high_risk_external_mutation_lifecycle_requires_distinct_acceptance_then_reaches_archive`
14. `test_archive_scout_requires_orchestration_validation_when_delegation_or_shared_mutation_is_declared`

For each refusal test, snapshot both lifecycle files with `read_bytes()` after the preceding valid event; attempt the gated event; assert exit 1 and exact pre/post byte equality. Also assert the manifest/artifact files are untouched. This checks the important ordering property: validation must occur before `_write_run` and `_append_event`.

`test_run_core_path_transitions_to_archive` should remain a revision-1 compatibility control rather than being converted wholesale to revision 2. Add a distinct complete revision-2 path so regression origin is obvious.

## Generated, packaging, and release coverage

- Add `orchestration` to the expected `victims` list in `test_release_staging_requires_every_real_cli_sibling`; the dynamically derived removal loop then proves it is included in staged releases.
- The existing release staging test also proves `cli/flow.py` imports are transitively resolvable. Ensure the new module is imported from the launcher, not dynamically at command execution, or add an equivalent staging assertion.
- Expand `test_lifecycle_commands_reference_c_lite_run_protocol` or add a dedicated semantic-source test for each changed command: assert the canonical `validate-orchestration` invocation/standard link rather than duplicating policy prose assertions. Regenerate help and retain `test_regenerate_flow_help_check_is_clean`.
- Existing sync JSON and runtime-smoke tests cover adapter machinery. Add a source-level equivalence test only for the shared orchestration trigger and required stage calls, then run both real `flow sync ... --check` commands.
- The unit suite's release-install tests prove packaging shape, not a tagged remote artifact. The planned isolated-home tag install/update plus doctor, both syncs, runtime smoke, and `validate-orchestration` invocation must be documented in `validation-results.md` as post-push release evidence.

## Targeted mutation checks

| Manual mutation | Covering test | Proof expected |
| --- | --- | --- |
| Change risk boundary from `>= 2` to `> 2` | `test_risk_is_high_with_exactly_two_aggravating_factors` | fails |
| Treat `unknown` capability as dispatch-sufficient | `test_dispatch_rejects_unknown_required_capability_for_dispatch` | fails |
| Disable ancestor/descendant overlap detection | `test_dispatch_rejects_parent_child_concurrent_repository_scopes` | fails |
| Compare only verifier/producer, not verifier/evidence collector | `test_acceptance_rejects_high_risk_when_verifier_matches_evidence_collector` | fails |
| Move lifecycle write ahead of gate validation | any four `...without_writing` gate tests | fails on byte comparison |

Record each mutation's command, failing test, restoration, and result in the run validation evidence. If a mutation is skipped, identify that row and the unproven fault it leaves exposed.

## Validation commands and residual checks

Run focused tests first, then the full required suite:

- `/opt/homebrew/bin/python3.12 -m unittest tests.test_flow.OrchestrationValidationTests tests.test_flow.OrchestrationCliTests`
- `/opt/homebrew/bin/python3.12 -m unittest discover -s tests`
- `/opt/homebrew/bin/python3.12 scripts/regenerate-flow-help.py --check`
- `flow sync claude --user --check`
- `flow sync codex --user --check`
- `flow doctor`
- `flow runtime smoke --target all`
- `git diff --check`

The named-class command assumes the new test classes are module-loadable in the same manner as current `unittest` discovery; use discovery if the runner cannot resolve the dotted module path. Before release, also inspect staged paths, the remote, release staging/import coverage, and absence of the dirty canonical checkout's `docs/backlog.md` from this worktree diff.
