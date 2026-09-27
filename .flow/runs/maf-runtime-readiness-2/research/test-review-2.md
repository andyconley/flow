## Test Coverage Analysis

### Current Coverage

- Reviewed the approved AC1--AC15 and validation plan, the current implementation through `e1c6b2d`, prior test/SRE findings, and retained fence-mutation evidence in `mutation-check.md`.
- Passed on current HEAD:
  - `tests.test_maf_runtime`, `tests.test_maf_diagnostics`, `tests.test_maf_child_handshake`, `tests.test_chartered_delivery_gateway`, and `tests.test_runtime_startup_recovery`: 59 passed, 1 skipped. The skip is deliberate: the real-child test requires an explicit `FLOW_MAF_PYTHON` built from the locked requirements.
  - `tests.test_retrieval_capability`: 5 passed. This confirms the new runtime provisioning does not break those isolated install/retrieval fixtures.
- Fence mutation evidence is retained and credible: replacing the readiness call with a fixed dictionary made `test_unready_runtime_refuses_before_any_attempt_side_effect` fail; restoring the call makes it pass.
- A full current-suite run before `e1c6b2d` completed with 1,654 tests, 52 failures, 25 errors, and 51 skips. It exposed installation and termination clusters. The bounded rerun below was performed after `e1c6b2d`.

### Current Failure Disposition

1. **Installer/update compatibility repaired (AC1, AC2, AC13).** Commit `27491f6` injects a verified offline runtime into isolated installer fixtures. All eight previously failing release/develop/update tests now pass, including release swap, current/no-semver/unreachable-remote checks, and highest-tag selection.
2. **Cancellation/termination failures are baseline host behavior, not a readiness regression.** The current and baseline (`d1a929c`) runs of `tests.test_delivery_cancel tests.test_delivery_termination` each produce exactly 6 failures and 6 errors. Both show the same `process_identity_mismatch` cancellation refusal, sibling-started cascades, and `skipped_other_user`/`gone` group-reap outcomes. These remain an operational portability concern, but they predate this implementation and are outside its changed behavior.

### Recommended Tests

1. **`test_release_install_with_hermetic_locked_maf_source_succeeds`** — retain the new offline-runtime fixture and assert selected interpreter, imports, pointer identity, strict readiness, and child handshake. This is the AC1/AC15 release oracle.
2. **`test_failed_install_preserves_source_config_and_runtime_pointer`** — inject a package/probe failure and compare the prior source/config/pointer bytes. This remains the AC2 recovery oracle.
3. **`test_cancel_and_abandon_on_supported_macos_process_identity`** — use a real child controlled by the fixture and assert the PID/start-token/group identity is accepted before cancellation, with no leaked child process. This is a separately owned portability repair.
4. **`test_managed_child_identity_handshake`** — retain the explicit managed-interpreter release check; the normal skip-only run is insufficient by itself.

### Priority

- Critical: retain hermetic clean-install success and rollback proof in release validation.
- High: real managed-child handshake in release validation; separately repair macOS process-identity portability.
- Medium: complete diagnostics state/remedy table has focused coverage and should remain in the release matrix.

### Verification Notes

- No provider or network calls were used in this review.
- Current focused rerun command:
  `/opt/homebrew/bin/python3.12 -m unittest tests.test_maf_runtime tests.test_maf_diagnostics tests.test_maf_child_handshake tests.test_chartered_delivery_gateway tests.test_runtime_startup_recovery tests.test_retrieval_capability tests.test_delivery_cancel tests.test_delivery_termination -v`
  Result: 115 tests, 6 failures, 6 errors, 1 skipped.
- Baseline comparison command (checkout at `d1a929c`):
  `/opt/homebrew/bin/python3.12 -m unittest tests.test_delivery_cancel tests.test_delivery_termination -v`
  Result: 51 tests, 6 failures, 6 errors. It has the same failure set as current HEAD.
- Targeted installation/update rerun result at `27491f6`: 8 passed.
- A direct managed-interpreter run confirmed the real child handshake passes with `FLOW_MAF_PYTHON=/private/tmp/flow-maf-lock-20260927/bin/python`. In that environment, `test_absent_managed_selection_is_not_installed` fails because it inherits the override rather than clearing it. The handshake is valid evidence, but this identifies a test-isolation gap: absent-managed-selection tests must clear `FLOW_MAF_PYTHON` explicitly.
- Verdict: **acceptance-ready for the MAF runtime-readiness change at `27491f6`**, with the stated baseline macOS process-identity failures recorded as an unrelated follow-up. Runtime fence, diagnostics, gateway refusal, successor, retrieval, installer/update compatibility, and the managed-child identity proof are supported without provider or network calls.
