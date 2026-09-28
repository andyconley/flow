# Marketplace / MAF Runtime Readiness Acceptance Disposition

The user approved direct closeout on 2026-09-27 with these dispositions:

- The v0.38 predecessor update limitation is accepted. The one-time activation bridge is sufficient for the sole current user; no additional legacy rollback implementation is required.
- AC13 is interpreted as no new regression against the recorded baseline. The MAF-focused set passed 753 tests with one expected skip, and the CLI set passed 731 tests with one expected skip.
- The macOS process-identity/cancellation cluster is unrelated baseline behavior. A bounded rerun reproduced the documented result exactly: 51 tests with 6 failures and 6 errors, centered on `process_identity_mismatch`. It is deferred rather than allowed to block Marketplace acceptance.
- `installed_at` remains operational pointer metadata rather than canonical runtime identity. Artifact, interpreter, ABI, platform, architecture, protocol, runner, and installed-body digests already provide the execution identity; making reinstall time identity-bearing would create false identity changes.
- Repeated full-suite and independent-review cycles are waived for this direct repair.

The orchestration producer omission was repaired through explicit user-approved amendment 0001. Acceptance-stage orchestration validation subsequently returned no findings.
