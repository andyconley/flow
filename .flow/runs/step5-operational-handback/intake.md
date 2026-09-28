# Intake: step5-operational-handback

The remainder of MAF adoption step 5 (`docs/maf-adoption-design.md` step 5), minus MCP handback.

## Engineer decisions (2026-09-27)

1. **Scope:**
   - trace correlation across Flow, MAF and provider sessions;
   - receipt verification;
   - an enforced token cap.

   MCP handback is **out** (skipped by Andy).
2. **One run, one PR,** with ordered commits, as in `step5-cancellation`.
3. **Token cap: cumulative and checked before each grant.**
   - The charter seals a token budget for the whole lineage.
   - Before each paid grant, Flow refuses, or escalates through delegated expansion, once the observed usage has reached the cap.
   - Subscription CLIs report usage only after a call, so the cap can overshoot by at most one call. The documentation says so honestly.
4. **Receipt verification: an offline CLI.** `flow run verify-receipt` independently recomputes a sealed receipt from:
   - the ledger;
   - the sealed authority;
   - the checkpoints;
   - the on-disk evidence digests.

   It runs no provider, and it doesn't re-apply the diff or re-run the test.

## Known pain (from live runs)

- `v8-live-validation-3` needed a hand-written `receipt_check.py`, and its first version had vacuous-pass shapes (`runtime-evidence-completion-manifest`, seen 11 times).
- Per-call timings aren't shown by `inspect-delivery` (`delivery-per-call-timings`, promoted).
- Manager request text is stored only as digests, so guidance could be checked only through checkpoints (`manager-prompt-text-inspection`).
- The recovery actor defaults to a hard-coded `codex-assisted-recovery` (`recovery-actor-provenance`).
- The design doc says no dollar or token stop exists on subscription providers; usage is only observed.
