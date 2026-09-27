# Implementation Handback: MAF Runtime Readiness

## Status

Implementation, documentation, validation, quality review, and operational review are complete. The run is ready for `flow-review`.

## Delivered

- A hash-locked, digest-addressed managed MAF runtime for macOS arm64 / CPython 3.12.
- Transactional install, update, conversion, rollback, quarantine, contention control, and one-shot predecessor activation.
- Exact readiness, integrity, protocol, and child-initialization proof before any attempt or callback side effect.
- Stable diagnostics and strict Delivery readiness, with validated overrides that never silently fall back.
- Exact runtime-startup failure classification and crash-safe, one-successor recovery.
- Runtime identity in envelopes and receipts with historical v5-v8 compatibility.
- Updated README/CLI/install/recovery guidance, ADR 0020, and generated help surfaces.
- The original Delivery owner-event projection regression fixed by separating control events from lifecycle history.

## Roles engaged

- Lead developers: implementation, compatibility repair, recovery hardening, and final regression fixes.
- Test engineer: independent acceptance matrix, baseline comparison, mutation review, and final verdict.
- Architect: predecessor-update bridge design and explicit v0.38 limitation.
- SRE: repeated operational review through final approval.
- Quality reviewer: repeated correctness review through final APPROVE.
- Technical writer: AC14 documentation audit and corrections.

## Proof

See `validation-results.md`. The final broad set passed 753 tests with one expected skip; the Flow CLI module passed 731 tests with one expected skip. Quality approved 24 bounded checks, and SRE approved 16 offline/no-provider checks. The gateway mutation proof, real managed child initialization, locked-wheel installation, rollback, integrity, recovery lineage, and unsupported-host behavior are all retained as durable evidence.

## Important compatibility note

A direct update started by v0.38 cannot run newly installed lifecycle code or restore source it already deleted. Flow therefore records and runs a visible, once-only managed-runtime activation on the first eligible new-version invocation. Failure preserves the prior runtime pointer, records the failure without repeated network attempts, and directs the operator to `flow runtime install-maf`. A new-installer/bootstrap run provides the fully transactional source-plus-runtime path.

## Next lane

Run `flow-review` against AC1-AC15. Do not publish or merge until that review is accepted. Live provider validation is separate and remains unauthorized by this implementation run.
