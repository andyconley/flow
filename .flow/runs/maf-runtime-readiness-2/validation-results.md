# Validation Results: MAF Runtime Readiness

## Result

Implementation is ready for handback for the supported Mac Studio target: macOS arm64 with CPython 3.12. Independent quality review approved the final implementation, and SRE judged it operationally ready. No provider calls were made.

## Acceptance evidence

- Managed installation uses the complete 11-package resolved inventory with exact wheel SHA-256 hashes, `--require-hashes`, and a digest-addressed environment. The clean oracle uses no `FLOW_MAF_PYTHON` bypass.
- Readiness imports the exact MAF symbols used by the Delivery Lead, validates installed RECORD file bodies, binds package, runner, protocol, interpreter, platform, architecture, SOABI, and RECORD digests, and refuses broken metadata-only environments.
- The child must emit matching `runtime_ready` and post-import/post-storage `runtime_initialized` records before any manager, specialist, terminal, or provider callback is accepted.
- Install, update, and develop conversion use staged provisioning and restore the prior source, config, and runtime pointer on failure. A visible one-shot bridge covers upgrades started by pre-transactional v0.38; diagnostics remain read-only and a failed bridge does not retry silently.
- Gateway readiness runs before attempt-directory, ledger, claim, grant, spend, process, or provider effects. The retained mutation check proves bypassing it makes the zero-side-effect regression fail.
- Runtime-startup successor recovery requires the exact sealed failure class and receipt/envelope identity, reconciles crash-stranded claims across the complete predecessor lineage, and refuses duplicate or concurrent successors.
- Provisioning uses an owner-checked interprocess lock, unique temporary pointers, invalid-target quarantine, and atomic activation.
- Unsupported MAF hosts retain base Flow with a warning; strict Delivery readiness and chartered execution still fail closed.
- Delivery control events no longer corrupt lifecycle-state verification; the original owner-projection regression now passes.

## Automated validation

- Final broad set: `python3.12 -m unittest tests.test_flow tests.test_delivery_owner_projection tests.test_maf_env tests.test_maf_runtime tests.test_runtime_startup_recovery tests.test_retrieval_capability` — **753 passed, 1 expected skip**.
- Flow CLI module: **731 passed, 1 expected skip**.
- Final independent quality review: **APPROVE**, 24 bounded tests passed, no skips, no network/providers.
- Final SRE review: **operationally ready**, 16 bounded offline/no-provider tests passed.
- Final runtime/retrieval proof: 15 passed; later-lineage recovery proof: 4 passed; optional-runtime boundary proof: 6 passed.
- Real managed child handshake reached both `runtime_ready` and `runtime_initialized` using `/private/tmp/flow-maf-lock-20260927/bin/python`.
- `git status --short`: clean before handback artifacts.

## Repository-suite disposition

The last complete repository run before the two final test-only/regression fixes ran 1,665 tests with 14 failures, 6 errors, and 51 skips. Twelve failures and all six errors are the pre-existing macOS process-identity/cancellation cluster reproduced at baseline commit `d1a929c`. The two non-baseline failures were the hardcoded-wheelhouse guard and owner-projection regression; both were fixed in `1b5696b` and `2fdf6b1`, then included in the passing 753-test final set. The full 1,665-test command was not repeated after those two bounded fixes.

## Review evidence

- `research/quality-review.md`: final verdict APPROVE.
- `research/sre-review.md`: operationally ready for the supported Mac Studio target.
- `research/test-review-2.md`: independent installer/runtime compatibility review.
- `research/docs-review.md`: AC14 documentation audit.
- `mutation-check.md`: pre-attempt fence mutation and restoration evidence.

## Limitations and follow-up

- The hashed managed artifact set is intentionally limited to macOS arm64 and CPython 3.12. Base Flow remains available on other supported Python hosts, but MAF Delivery is unavailable until a signed/hashed artifact set is added.
- The v0.38 updater cannot execute new transactional code after it swaps source. The documented one-shot bridge activates the runtime on the first eligible new-version invocation and retains the prior runtime pointer on failure; reinstalling with the new installer is the fully transactional alternative.
- Existing macOS process-start identity test failures remain a separate baseline defect and were not weakened in this run.
- No live provider acceptance was performed; it remains a separately authorized follow-up.
