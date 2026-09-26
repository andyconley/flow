# Review: shaper-expansion-approval (MAF adoption step 5, slice 1)

- **Lane:** `flow-review`, 2026-09-25 to 2026-09-26.
- **Change:** commits `2b9e045`–`1d5ec46` on `codex/step5-shaper-approval-design`.
- **Reviewers:**
  - an acceptance quality-reviewer, distinct from the producer and from the implementation reviewers;
  - an acceptance test-engineer, whose expertise lookup admitted one entry (`define-a-test-oracle-with-a-concrete-example`, disposition: applied).
- **Earlier implementation review:** `implementation-review.md` (quality Q1–Q7, security S1–S5).

## Review Summary

### Verdict
- **Ready to accept and archive.**

### Findings
- **Critical:** none.
- **Important:**
  - **I1:** requirement R2 asked the request to record headroom remaining and the evidence digests. Neither is recorded. **Engineer accepted the omission (2026-09-26),** recorded in ADR 0017. Nothing authorises from these fields.
  - **I2:** "can still finish within the charter" (AC7) is proven as the attempt sealing a valid terminal receipt with no further pause. With a single producer, a denied expandable unit is always one the run needs to pass. **Engineer accepted this reading (2026-09-26).** The validation record now names the right test.
  - **A10 deviation:** a `decide` holder waits up to 10 seconds behind another `decide`, so the loser sees `expansion_already_decided`. **Engineer approved (2026-09-26).**
- **Suggestions:**
  - **Fixed in `1d5ec46`:**
    - S-a: binding a hard denial's checkpoint is best effort.
    - S-c: `decide-expansion` refuses a worker pause with no bound position, with a new test.
    - S-d: the pre-seal close transaction is documented in ADR 0017.
    - S-e: `_outstanding_units` computes each scope once.
  - **Accepted as is:**
    - S-b: after a hard-denied latest action, ordinary (non-expansion) recovery now refuses with `checkpoint_position_unrecoverable` rather than `no_restorable_checkpoint`. It refuses either way, with the same guidance.
    - Test-engineer notes: the crash test injects one failure point in a single transaction, and one truly-paused test sets its state through SQL. Both are acceptable.

### Requirement Fit
- AC1–AC12 as amended in `plan.md` ("Amendments from plan review (binding)": AC6 wording, AC7 E5a, AC8 E6a) are each implemented and each map to a named test with a concrete oracle. The quality reviewer's per-AC table found every criterion met, with I1 and I2 now resolved by engineer decision.
- The earlier review fixes (Q1, Q2, Q7, S1, S2, S4) were confirmed closed; Q3 is closed by S-c.
- There is no scope drift. No replan expansion, specialist pool, re-sealing or live run was added, and `decide_replan` is unchanged.
- The deviations are justified and recorded in ADR 0017:
  - a unit past a ceiling is a hard denial;
  - the pending request row is the pause marker;
  - release fences only attempts with open expansions;
  - the sealing rule compares base + headroom;
  - decisions queue.

### Validation Fit
- **Suite:** 1538 tests OK, 0 skipped, with `FLOW_MAF_PYTHON`, run after the final fixes.
- **End to end:** five MAF-gated cases against the real pinned runner. They pin replay identity: the paused worker proposal returns with the same action id, manager calls replay with identical call ids in answer mode and on restart, and the supervisor allows growth past base + 1.
- **Mutations:** M1–M10 each caught and restored, and rerun after the review fixes.
- **Proof review:** the test engineer judged the proof sufficient, with deterministic concurrency tests (`Barrier(2)`, stable over 10 of 10 repeated runs).
- **Not run:** no live provider or live v8 run, which is a non-goal of this slice.

### Residual Risks
- **Replay identity depends on the pinned MAF version.** `tests/test_maf_expansion.py` must pass on every pin change.
- **Restart mode and denial binding are new.** The `restart` mode and the wider checkpoint binding (which now also binds on denials) are new recovery surface, proven hermetically only.
- **No live v8 run yet.** Real-world validation runs are the next step.
- **A seal failure after the pre-seal close** leaves a lapsed grant on a started attempt. A supersede recovers it.
