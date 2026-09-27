# SRE Review: MAF Runtime Readiness (final at `a789124`)

## Reliability Review Summary

### Service Expectations

- Chartered Delivery now checks runtime readiness after read-only authority and
  worktree proof, before execution directories, attempts, ledger rows, grants,
  receipts, processes, or provider callbacks exist.
- The probe imports the exact MAF symbols required by the Delivery Lead,
  validates all locked package versions and `RECORD` contents, and binds lock,
  runner, protocol, machine, ABI, and package-record identity into the runtime
  digest.
- The child must report both matching computed identity and initialized runner
  state before the parent permits any manager or specialist callback.

### Observability Gaps

- Ordinary doctor remains a visible informational warning when the optional
  runtime is absent; strict readiness and MAF smoke return nonzero.
- The managed runtime is intentionally limited to macOS arm64 / CPython 3.12.
  Unsupported hosts preserve base Flow installation and report a repairable
  non-ready Delivery state. Keep that support envelope prominent in release
  notes and the operator runbook.

### Failure Modes

- Provisioning serializes concurrent changes, uses hash-locked wheels, stages
  and probes before selecting a pointer, and quarantines invalid target
  directories.
- Install/update/develop conversion preserve prior source, configuration, and
  runtime selection when provisioning fails. First-upgrade activation is
  recorded and bounded; diagnostics remain read-only.
- Runtime-startup recovery requires exact sealed receipt/ledger evidence and
  zero observed or uncertain sends. Reconciliation now searches all lineage
  predecessor positions with `json_each`, binds an existing successor
  idempotently, and refuses a duplicate.

### Deployment Safety

- Ran bounded no-network/no-provider verification:

  ```sh
  env -u FLOW_MAF_PYTHON FLOW_MAF_WHEELHOUSE=/private/tmp/flow-maf-wheelhouse \
    /opt/homebrew/bin/python3.12 -m unittest \
    tests.test_runtime_startup_recovery tests.test_maf_runtime \
    tests.test_flow.FlowCliTests.test_unsupported_managed_maf_host_keeps_base_install_and_readiness_is_strict -v
  ```

  Result: **16 passed**.
- This includes clean managed wheelhouse provisioning and real-child
  initialization, metadata-only/symbol rejection, later-lineage stranded-claim
  reconciliation, duplicate refusal, reconciled CLI success exit, rollback,
  and unsupported-host base-install behavior.
- No provider or network calls occurred in this review.

### Operational Recommendations

1. Release/install on the supported Mac Studio target, then run strict MAF
   readiness and the separate authorized live Delivery Lead acceptance.
2. Retain the old terminal attempts as evidence. Start a fresh linked run for
   the original chartered-delivery repair rather than altering them.
3. Maintain the package-record, handshake-order, lineage-reconciliation, and
   unsupported-host cases in the release gate.

## Verdict

**Operationally ready for the supported Mac Studio target.** The prior P0/P1
issues are resolved: exact runtime readiness, parent/child fencing,
transactional installation, compatibility addressing, recovery receipt and
lineage integrity, CLI idempotency, and unsupported-host base behavior now
have focused evidence.
