# Handoff: Chartered v8 Delivery Recovery, chunk 2

- **Status:** implemented, reviewed, and validated. It is ready for acceptance review (`flow-review`).
- **Run:** `chartered-delivery-recovery-2`, a linked follow-on of `chartered-delivery-recovery` (1a, PR #26) and `-1b` (PR #29, open).
- **Branch:** `codex/chartered-delivery-recovery-2`, stacked on 1b. Worktree: `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`. Not pushed. Rebase onto `main` after #29 merges.

## What shipped

An interrupted v8 attempt whose producer or verifier response Flow had already stored can now be completed without a resend:

1. `inspect-delivery` shows the blocker's route and the owner generation.
2. `resolve-execution <work> <attempt> <action> --disposition resolved_completed --expected-generation N --actor … --explanation …` records the resolution.
3. `recover-delivery-lead` continues.

Details:

- **The route.** It refuses `--evidence-file`, requires `--expected-generation`, accepts only `resolved_completed`, holds the recovery lock, and re-checks the envelope, lead, worktree, and generation.
- **The ledger method.** `resolve_observed_v8` re-validates the stored observation and its recorded send inside the resolving transaction, and appends the resolution at the current generation with no bump.
- **Binding at continuation.** Recovery accepts only one resolution per action, in this attempt, at a recovery-chain generation.
- **Abandon-only rows.** Manager calls and actions without an observation are reported "unresolvable; abandon only" in inspection. The existing `release` or `block` is the remedy.
- **Guards:**
  - a v8 worktree that is, contains, or sits inside the project `.flow` is refused, compared by device and inode;
  - the v8 no-dispatch regrant is refused;
  - `send_lock` refuses a symlink or a hard link;
  - the MAF tests read only `FLOW_MAF_PYTHON`.
- **ADR 0016** has the chunk 2 amendment, with its assumptions and residuals.

**Commits:**
- Guards and hardening: `4331765`, `9155c4d`, `08b35bf`, `c4a613d`, `abede3d`.
- Reconcile: `a7f43e6`, `f6b5ea9`, `7e94e84`, `3d6cec2`, `3561c8e`, `ef60915`, `df6808b`.
- Test ordering: `af223c0`.
- Review fixes: `c90d58c`.
- ADR residuals: `a54925d`.

## Proof

See `validation-results.md`:

- the full suite: 1465 OK, 0 skipped;
- the MAF-gated tests: 11 OK, which the PR body must carry (merge gate R9);
- mutations M1, M3, and M4.

## For acceptance review: engineer decisions

1. **M2 (AC11) deviation.** No single mutation produces a resend, because five independent guards block it. Accept it as a deviation, or ask for a contrived multi-point mutation.
2. **`resolve_unknown` still accepts v8** at the ledger level. An existing structured-verifier test relies on it. Refusing it there would change that slice's behavior. The CLI reaches v8 only through the guarded route.

## Residuals

- R3: a resolved producer without a verifier input is checked for scope only.
- A released or attention lead with an uncertain observed action can only be abandoned.
- A symlink inside the worktree that points into `.flow` relies on the Codex sandbox (unverified).
- Reason-code imprecision in two refusals.
