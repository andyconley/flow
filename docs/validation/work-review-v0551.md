# Work review validation and baseline failure investigation

Baseline: `2d13378cbdcbb9dd424d5437f9bc9a766abe3db8` (v0.55.1). Untouched main ran 415 tests with 16 errors, one failure and 14 skips. The initial changed checkout had exactly the same failing test identities.

## Exact breakdown

| Test | Cause | Correction |
| --- | --- | --- |
| `test_claude_config.ClaudeConfigTests.test_config_writes_stay_private_and_missing_auth_is_explicit` | Fixture portability defect: nonrepository temporary workspaces inherit the sandbox placeholder `/tmp/.git`; Git rejects that invalid metadata. | Initialize an explicit repository in the fixture; preserve production fail-closed Git metadata checks and all permission/interpreter assertions. |
| `test_command_classification.CommandClassificationTests.test_real_event_handler_keeps_exits_separate_from_tool_failure` | Missing pinned `runtime/adapters/node_modules/@agentclientprotocol/codex-acp/dist/index.js`. | Run `npm ci --ignore-scripts` with the checked-in adapter manifest/lock. Tests exercise actual guarded adapter code. |
| `test_install.InstallTests.test_activation_preserves_generated_user_overlay_command_and_lists_it` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_activation_write_failure_restores_original_legacy_surfaces` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_ambiguous_agent_link_keeps_its_owned_generated_target` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_dry_run_does_not_create_installation` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_explicit_cutover_restore_and_skill_directory_symlink` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_locally_modified_opt_in_surface_is_not_overwritten` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_modified_legacy_skill_blocks_cleanup_and_shared_post_edits_block_rollback` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_normal_use_smoke_context_shape_reopen_stops_before_approval` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_side_by_side_idempotent_launcher_and_no_legacy_replacement` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_supported_skill_mapping_and_no_obsolete_coordinator_commands` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_install.InstallTests.test_upgrade_cleans_only_owned_hooks_and_registration_and_rolls_back` | Missing `v2/.venv/bin/python`; installer deliberately refuses an unprepared source runtime. | Provide the test virtualenv at the documented path. CI already provisions it. No installer assertion removed. |
| `test_native_permissions.NativePermissionTests.test_actual_guarded_command_renderer_keeps_denial_and_diagnostic` | Missing pinned `runtime/adapters/node_modules/@agentclientprotocol/codex-acp/dist/index.js`. | Run `npm ci --ignore-scripts` with the checked-in adapter manifest/lock. Tests exercise actual guarded adapter code. |
| `test_project_python.ProjectPythonTests.test_native_wrappers_use_selected_python_and_preserve_global_state` | Fixture portability defect: nonrepository temporary workspaces inherit the sandbox placeholder `/tmp/.git`; Git rejects that invalid metadata. | Initialize an explicit repository in the fixture; preserve production fail-closed Git metadata checks and all permission/interpreter assertions. |
| `test_runtime_smoke_repairs.RuntimeSmokeRepairs.test_native_runtime_owns_temp_root_without_guessing_workspace_slug` | Fixture portability defect: nonrepository temporary workspaces inherit the sandbox placeholder `/tmp/.git`; Git rejects that invalid metadata. | Initialize an explicit repository in the fixture; preserve production fail-closed Git metadata checks and all permission/interpreter assertions. |
| `test_lifecycle.LifecycleTests.test_cancel_tracks_child_in_different_process_group` | Runtime defect: terminated zombies retained by container PID 1 were classified as live workers. | Read process state and exclude exited zombies; retain birth identity checks. Add zombie and PID-reuse regressions; keep real detached-child cancellation test. |

Summary: 13 missing prerequisites (11 virtualenv, two adapter), three fixture portability defects, and one runtime zombie-liveness defect. Local dependencies remain ignored; only the lifecycle correction and explicit fixture setup are source changes.

## Reproduction

```sh
python3.12 -m venv v2/.venv
v2/.venv/bin/python -m pip install -r v2/requirements.lock
mkdir -p v2/runtime/adapters
cp v2/adapters.package.json v2/runtime/adapters/package.json
cp v2/adapters.package-lock.json v2/runtime/adapters/package-lock.json
npm ci --ignore-scripts --prefix v2/runtime/adapters
(cd v2 && .venv/bin/python -m unittest discover -s tests -v)
v2/.venv/bin/python -m unittest tests.test_release_gate tests.test_release_highlights -v
python v2/scripts/check_distribution.py
git diff --check
```

The native macOS/provider qualification tests remain subject to their existing platform/credential skip conditions. Offline test success does not establish live model/provider qualification. The legacy help generator also fails on untouched main because README lacks its `cli-commands-table` marker; v2 command documentation is maintained in `v2/FLOW_V2_OPERATIONS.md`.

## Local result after corrections

The full v2 suite passes: **423 tests, 13 skips, zero failures/errors**.
This includes six work-review tests and two new lifecycle regression tests.
The initial run used a Python 3.12 test virtualenv plus the pinned adapter lock;
GitHub CI provisions the fully locked Python requirements independently.

## Native consumer parity correction

The first PR head passed all offline tests, but macOS consumer validation caught
stale checked-in role recipe schemas after the renderer gained structured findings.
All 13 recipes were regenerated using `poc.role_renderer.write_bundle` through
the existing catalog/composition path. A new offline parity test now compares
every distributed recipe with its renderer output even when Goose is unavailable;
the existing real-Goose rendering assertions remain intact.
