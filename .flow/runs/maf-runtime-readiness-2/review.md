# Review: MAF Runtime Readiness

## Verdict

**Needs refinement.** The implementation substantially fits the technical intent, but the run cannot be accepted under the approved review contract.

## Critical findings

### R1: the sealed acceptance orchestration contract is invalid

`flow run validate-orchestration maf-runtime-readiness-2 --stage acceptance --json` fails `writable-producer-binding`. Assignment `implementation-handback` is writable and produced `HANDOFF.md`, but `verification.producer_assignments` names only `implementation-core`.

The orchestration manifest is an approved, digest-sealed artifact. Silently editing it now would invalidate the approved digest and rewrite producer provenance after delivery. Flow currently has no review-refinement transition or supported orchestration-amendment/reseal path. Until that lifecycle defect is fixed, the required independent review dispatch and `accept-review` gate cannot run compliantly.

## Important findings

### R2: AC2 has an unapproved predecessor exception

The approved requirement says update shares the staged build/probe/atomic-switch contract and preserves the prior source on failure. A direct update executed by v0.38 cannot run new code after swapping source and has already removed its rollback source. The implementation adds a reasonable visible, once-only activation bridge on the first eligible new-version invocation, but that is later than the update and cannot restore the old source.

This is documented honestly, but the requirement or acceptance criterion was never formally amended or approved. Acceptance needs an explicit engineer disposition: approve the narrow v0.38 exception, or require reinstall/bootstrap for the first upgrade.

### R3: AC13 and the validation plan require a green complete suite

AC13 says existing v6-v8 inspection, receipt, recovery, cancellation, and lineage tests remain green. The validation plan calls for the complete Python 3.12 suite. The final complete run executed 1,665 tests and still had the reproduced macOS process-identity/cancellation baseline cluster. The implementation did not worsen it, and the MAF-focused/broad set passed 753 tests with one expected skip, but “no regression from a red baseline” is not the same as “remain green.”

Acceptance needs either the baseline defect fixed or AC13 explicitly amended to a no-new-regression criterion with the baseline evidence attached.

### R4: the final independent verdict does not cover final HEAD

The last independent quality and SRE approvals were recorded at `a789124`. Later commits changed runtime-smoke fixtures, test environment routing, lifecycle verification in `cli/runstate.py`, and the durable handback. The final 753-test set covers those changes, but a verifier distinct from the producers has not reviewed final HEAD. The acceptance orchestration failure currently prevents a compliant fresh dispatch.

### R5: support evidence and ADR wording need reconciliation

- Requirement 4 says the canonical runtime identity records installation time. `installed_at` is stored in the pointer, not the identity bound into attempts.
- ADR 0020 says the runtime address is based on requirements, base interpreter, and platform; the implementation correctly also binds runner, protocols, ABI, architecture, and installed RECORD evidence. The ADR should describe the actual decision.
- On an unsupported host, `install-flow.sh` can retain `maf_runtime_activation_state = "succeeded"` even though strict MAF readiness is unavailable. Runtime behavior is fail-closed, but the support marker is misleading.

## Requirement fit

The final code strongly fits AC1 and AC3-AC12, AC14, and AC15 for macOS arm64 / CPython 3.12:

- hash-locked digest-addressed provisioning;
- exact symbol and installed-body integrity checks;
- authoritative validated override behavior;
- read-only diagnostics and strict readiness;
- pre-attempt zero-side-effect refusal;
- envelope/receipt identity binding and two-step child handshake;
- exact zero-send startup classification and crash-safe single-successor recovery;
- transactional current-version install/update/conversion rollback;
- preserved base Flow behavior on unsupported MAF hosts.

AC2 and AC13 require the explicit dispositions above before acceptance.

## Validation fit

- Final broad set: 753 passed, 1 expected skip.
- Flow CLI: 731 passed, 1 expected skip.
- Mutation evidence caught removal of the pre-attempt readiness fence.
- Managed clean-install and real-child initialization used the hash-locked local wheelhouse without a runtime override or provider calls.
- The final complete suite remained red only in the documented macOS baseline cluster after the two MAF-run regressions were fixed, but that still does not literally satisfy AC13.
- Acceptance-stage orchestration validation failed before reviewer dispatch; no acceptance transition was attempted.

## Residual risks and next action

Create a bounded Flow refinement that provides a supported way to amend/reseal orchestration producer provenance without rewriting history. In that refinement, obtain explicit approval for the v0.38 exception and AC13 baseline disposition, correct the support/ADR wording, then rerun independent quality, test, security, and SRE review at final HEAD. Only then retry acceptance validation and `accept-review`.
