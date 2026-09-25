# Review: chunk 2, Chartered v8 Delivery Recovery

- **Reviewers:**
  - `review-acceptance` (quality-reviewer)
  - `review-proof` (test-engineer; advisory request `072befd7…`, one entry, disposition `applied/trigger_satisfied`)

  Both were read-only and ran concurrently at `32ab015`.
- **Intent read:**
  - `requirements.md`, including C1–C3 and the `flow-solution` amendments;
  - `acceptance-criteria.md` (AC1–AC12; AC4 removed);
  - `plan.md` (P1–P4), `validation-plan.md`;
  - ADR 0016;
  - `research/implement-review.md`.
- **Brief errata:** `briefs/review.md` said "1461 OK" and "three guards". The logs say 1465 OK and five guards, and both reviewers judged against the logs.

## Review Summary

### Verdict
- **Ready to accept, pending two engineer decisions.** Both reviewers approve. There are no blockers and no majors.
- **Criteria:** AC1–AC3 and AC5–AC12 are met. AC11 is partially met: M2 is an honestly recorded deviation.
- **Implementation-review fixes:** confirmed correct in `c90d58c` (the device-and-inode worktree guard, the `send_lock` fstat check, the CLI refusal on `OSError`, and the added tests).

### Findings
- **Critical:** none.
- **Important:** none.
- **Minor:**
  - **A1. The `..` subtest sits inside the case-sensitivity skip** (`tests/test_chartered_delivery_gateway.py:218-220`). On a case-sensitive volume, AC12's `..` coverage disappears and the run is no longer "0 skipped". Fix: move it out of the skip. Observed.
  - **A3. No positive control for the zero-resend counter** (`tests/test_chartered_delivery_recovery.py:1471`). Nothing shows the counter records the resolved role's original send. Fix: add `sends.count(role) == 1`. Inferred.
  - **A2. Thin AC1 coverage:**
    - (a) is tested only with an `unknown` manager call, not a killed `started` one;
    - "no stored response" is tested only for the producer;
    - route revalidation is tested only for the producer.

    The code paths are shared, so the risk is low. Observed.
  - **P2 and P3.** The M2 claim is supported inductively (three shapes, never a resend) but not exhaustively. `resolve_unknown` on v8 has no direct test. Both reviewers treat these as open decisions, not defects.
- **Suggestions:**
  - A4: rename the test at `:1398`, which mentions a manager case it doesn't contain.
  - A5: `_state` does not snapshot `run.json`. That is harmless, because the route never writes it.

### Requirement Fit
- Requirements 1–12 as amended are implemented:
  - the fenced route (P1–P4);
  - observation-only resolution at the current generation;
  - the binding check;
  - abandon-only reporting;
  - lead changes after resolution;
  - the guards and hardening;
  - the ADR amendment.
- No drift: no manager resolution, no trace route, no operator import, and v5–v7 unchanged.

| AC | Status |
|---|---|
| AC1 | Met (thin; A2) |
| AC2 | Met (M1 confirms) |
| AC3 | Met (concurrency is shown by lock contention plus replay) |
| AC4 | Removed |
| AC5 | Met, through AC1 and AC3 |
| AC6 | Met (M3 confirms) |
| AC7 | Met |
| AC8 | Met |
| AC9 | Met |
| AC10 | Met |
| AC11 | Partially met: 1465 OK, 0 skipped; MAF 11 OK; M1, M3, and M4 caught; M2 is a deviation |
| AC12 | Met (A1 caveat) |

### Validation Fit
- Each deciding test reaches the assertion its AC names. Refusals compare full state snapshots, and the zero-resend assertion runs first.
- Every mutation restore was verified by sha256.

### Residual Risks
- A symlink inside the worktree that points into `.flow` relies on the Codex sandbox (unverified).
- A released or attention lead with an uncertain observed action can only be abandoned (fails closed).
- R3: a resolved producer without a verifier input is checked for scope only.
- A lock label can give an imprecise reason code.
- The PR body must carry `validation/maf-gated.log` (merge gate R9).

## Open engineer decisions

1. **M2 (AC11) deviation.** Both reviewers recommend accepting it. The quality reviewer asks for the A3 positive control first.
2. **`resolve_unknown` still accepts v8.** The reviewers split:
   - The proof reviewer would accept it as a documented residual.
   - The acceptance reviewer would close it now: refuse protocol 8 in `resolve_unknown`, and port `tests/test_structured_verifier_ledger.py:427-440` to `resolve_observed_v8`. The test's use of operator-supplied evidence on v8 is exactly what C1 excludes.

## Engineer decisions and refinement round (2026-09-25)

- **Decision 1, M2 (AC11):** the engineer accepted the deviation as it stands, with no positive control. AC11 is accepted with M2 recorded as a deviation.
- **Decision 2, `resolve_unknown` on v8:** the engineer chose to close it now. In `2c1f9eb`:
  - `resolve_unknown` refuses protocol 8 (`v8_resolution_requires_chunk_2`) inside its transaction.
  - The structured-verifier test now shows operator evidence refused on v8, and the same observed verifier resolved through `resolve_observed_v8`.
  - ADR 0016's residual is updated to say this path is closed.
- **Test fixes (engineer chose A1, A2, A4):**
  - **A1:** the worktree guard's `..` case runs on every volume; only the case-folded cases depend on a case-insensitive volume.
  - **A2:** AC1 (a) now covers a killed `started` manager call as well as an `unknown` one; "no stored response" and route revalidation now cover the verifier too.
  - **A4:** the misnamed test is renamed.
- **Evidence:** the full suite passed 1465 tests, 0 skipped, at `2c1f9eb`.
- **Verification note:** the refinement implements the acceptance reviewer's proposed fix. It is small, consisting of one ledger guard plus tests, and was not re-reviewed separately.

## Final disposition

**Ready to accept.** AC1–AC3 and AC5–AC12 are met. AC11 is accepted with the M2 deviation. The residuals are listed above.
