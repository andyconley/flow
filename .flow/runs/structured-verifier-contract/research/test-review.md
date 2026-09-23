# Test Strategy Review

- Pure evaluator tables cover valid pass/fail and every malformed, oversized, contradictory, mismatched, and replay-conflicting form with stable reasons.
- Ledger integration proves response observation precedes evaluation; transport loss alone produces unknown.
- Gateway tests prove the initial call, one permitted retry, third-call denial, narrowed cap one, cross-verifier shared counting, and exact replay without duplicate sends.
- A concurrent ledger test proves the cap is atomic.
- Receipt tests bind evaluations to action, verifier input, raw output, diff, and test evidence and refuse mutations.
- Frozen v7 fixtures remain readable without inferred v8 fields or write eligibility.
- No Ollama smoke is required.

## Advisory disposition

Applied `flow:entry/test-engineer/define-a-test-oracle-with-a-concrete-example`: each proposed test names a representative input, observable result, test level, and failure or recovery state. Post-receipt digest: `ddb95e4c7ded3c7e8f4033bdcdd0201d8d5aff695e74e0a2307d822cdc14265e`.
