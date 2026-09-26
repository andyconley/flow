# Validation Plan: manager progress repair and bounded retry

| AC | Proof |
|---|---|
| AC1 | `test_progress_parse`: the recorded failing reply is repaired, its `next_speaker` is `local-verifier`, and `_extract_json` of the canonical text equals the object (the MAF-gated half) |
| AC2 | Escape unit cases, and valid replies never marked repaired |
| AC3 | MAF end to end: one retry then success (+1 call, same round), and 3 unparsable replies fail with the reason |
| AC4 | MAF end to end: a retry past the base manager calls is granted automatically within headroom, and a retry past the runner ceiling is denied |
| AC5 | MAF-gated parity corpus |
| AC6 | MAF end to end: pause after a retry or repair, recover, and check identical call ids and rounds with no duplicate send |
| AC7 | Ledger events, receipt block presence and absence, and the tamper rejection test |
| AC8 | The full suite, fail-closed, with 0 skipped and `FLOW_MAF_PYTHON` set |
| AC9 | ADR 0018 exists, and the design doc references it |

- **Mutation checks:** five, listed in `plan.md`.
- **Validated against:** the change itself, with hermetic and MAF-gated tests. The live proof is `v8-live-validation-2` attempt 2, after release.
