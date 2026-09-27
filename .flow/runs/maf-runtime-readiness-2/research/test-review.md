## Test Coverage Analysis

### Current Coverage

- Passed, against the changed checkout: `/opt/homebrew/bin/python3.12 -m unittest tests.test_maf_runtime tests.test_maf_child_handshake tests.test_runtime_startup_recovery tests.test_chartered_delivery_gateway -v` (56 tests, 10.347s).
- `git diff --check af323b8^..61ffb9e` passed.
- The gateway fence is located before `execution/` creation, envelope writing, and ledger creation. The existing focused test proves the `require_ready()` exception leaves no `execution/` directory.
- The successor test proves one mocked zero-send MAF error delegates to normal execution, and a mocked `unknown` action refuses.

### Blocking Findings

1. **P0 — installer/update atomicity does not meet AC2.** The lifecycle conversion and release-update paths swap/write the Flow source and install configuration before calling `_provision_maf_runtime()` (`cli/lifecycle.py:601-611`, `651-659`, `870-878`). If provisioning fails, they return nonzero but do not restore the prior source/configuration. `install-flow.sh:258-260` is still more severe: it logs provisioning failure and continues successfully. This contradicts the required staged build/probe/atomic-switch contract and the clean-install requirement in AC1. Add failure-injection tests that assert source bytes, install config, and runtime pointer are all unchanged after failed provision.

2. **P0 — the claimed child identity handshake is an envelope echo, not an identity proof (AC9/AC10).** `delivery_lead.py` emits the `runtime_digest` supplied by the parent before importing MAF; the parent accepts that same echoed field (`runtime/maf_runner/delivery_lead.py:98-110`, `cli/maf_supervisor.py:460-493`). The only handshake test starts `sys.executable`, not a provisioned managed interpreter, and kills the child immediately after the echo (`tests/test_maf_child_handshake.py:17-27`). A replaced interpreter can echo the envelope digest, so this neither verifies the child runtime identity nor proves the managed runtime imports the actual packages. Compute/verify child identity from its running interpreter (or require a cryptographically bound probe result) and test both a managed positive handshake and a mismatched child refusal before callbacks.

3. **P1 — the stable diagnostics contract is incomplete and unproved (AC4/AC5).** `lock_mismatch` is listed in `UNREADY_STATES` but no `probe()` branch returns it (`cli/maf_runtime.py:96-143`). There are only three probe tests, no state/remedy matrix, no doctor severity/JSON test, no strict readiness CLI test, and no `runtime smoke --target maf` exit-code test. Add fixtures for each promised state, including pointer lock mismatch and timeout, and assert zero repair side effects.

4. **P1 — successor recovery is under-specified and under-enforced (AC11/AC12).** `recover_runtime_startup()` only checks a reason substring, empty action/manager statuses, and receipt-path existence (`cli/delivery_gateway.py:624-639`). It does not validate that the receipt bytes match `sealed_receipt_sha256`, prove exactly one successor, or independently compare predecessor source/baseline; it delegates those concerns to a normal new attempt. The two mocked tests do not cover duplicate recovery, stale claim, source/baseline drift, receipt tampering, non-runtime failures, or a manager send. Validate receipt digest, bind predecessor ID into a durable successor record, and add negative fixtures for every AC12 case.

### Recommended Tests

1. **`test_failed_maf_provision_rolls_back_source_config_and_pointer`** — Inject a failed package install during release update and conversion; assert all three durable selections are byte-identical.
2. **`test_install_script_fails_when_managed_runtime_cannot_be_provisioned`** — A clean-home installer run must exit nonzero and never claim installation success.
3. **`test_managed_child_reports_computed_identity_before_callbacks`** — Provision an isolated managed runtime, start the real child with credentials/network unavailable, verify a computed identity equals the sealed envelope, then verify a substituted interpreter is refused with zero callback calls.
4. **`test_probe_and_strict_readiness_cover_every_public_state`** — Table-drive all AC4 states and assert doctor warning vs readiness/smoke failure exits and remedies.
5. **`test_runtime_startup_successor_rejects_tampered_receipt_duplicate_and_drift`** — Validate receipt bytes/digest, one-successor idempotency, source/baseline/claim invariants, and observed/unknown manager/action sends.
6. **`test_fence_mutation_is_caught`** — Remove/bypass the `require_ready()` fence in an isolated mutation copy and show the zero-side-effect test fails. No retained evidence of this required mutation check was found.

### Priority

- Critical: installer transaction/exit semantics; actual managed-child identity verification.
- High: complete diagnostic matrix; sealed successor eligibility and lineage.
- Medium: clean-install/release gating, upgrade reuse, changed-lock rebuild, generated-surface parity.

### Verification Notes

- Manual/runtime checks: focused suite and whitespace check passed as listed above.
- Broad suite: `unittest discover -s tests` emitted progress but did not reach a completion summary within two observed 30-second tool windows; it is not counted as passing evidence.
- Verdict: **not acceptance-ready**. AC7 is partially supported by the focused fence test, but AC1-5 and AC9-12 lack required proof and the P0 findings directly contradict AC2, AC9, and AC10.
