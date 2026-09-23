# Solution Design Review

## Options

1. Separate Flow evaluator and durable ledger evaluation records. This preserves the provider response as an observed fact, makes Flow judgment replay-safe, and supports transactional retry/cap policy. It adds additive persistence and snapshot plumbing.
2. Embed parsed verdict and Flow evaluation in the provider action result. This changes fewer tables but conflates provider facts with Flow judgment and makes malformed-output observation and replay semantics harder to prove.

## Recommendation

Use option 1. Protocol v8 adds a pure verifier evaluator, separate append-only evaluation records, a Shaper-owned total-call cap, and receipt projection from ledger state. V7 readers and meaning remain unchanged.

The first non-pass evaluation is terminal for that verifier action but retryable for the attempt when allowance remains. The second non-pass, or the first when the cap is narrowed to one, makes the attempt terminal failed.

