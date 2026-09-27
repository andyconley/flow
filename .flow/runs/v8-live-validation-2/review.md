# Review: v8-live-validation-2

- **Date:** 2026-09-26.
- **Lane:** `flow-review`.
- **Reviewers** (both read-only, and distinct from the coordinator, which produced and collected the evidence):
  - quality-reviewer;
  - test-engineer (expertise lookup `no_match`).
- **Compared against:** `requirements.md`, `acceptance-criteria.md` (AC1–AC12), `plan.md` (the runbook and its amendments), `validation-plan.md`, `adversarial-review.md` and `plan-review.md`.

## Verdict

**Ready to accept and archive, as "validation found defects" (R7).**
- Both reviewers found every factual claim they spot-checked matched its evidence, and no claim overstated in the test review.
- The quality review asked for refinements to the records only: classification, verdict wording, a deviations section and evidence capture. All are applied below.
- No live action was needed, and no Flow code changed.

## Findings and dispositions

| ID | Source | Sev | Finding | Disposition |
|---|---|---|---|---|
| V1 | quality | Important | Attempt 2's AC8 label wasn't one of AC8's allowed outcomes. The manager was never told the one-producer-turn rule (`cli/delivery_gateway.py:1371-1381`), and its task said "Do not edit any files yet" | **Applied.** Attempt 2 is reclassified as **D7, a Flow design gap**, plus D6. The AC8 row is now "Not met: both attempts ended in Flow defects". The "Do not edit any files yet" wording was confirmed in the receipt |
| V2 | quality | Important | AC3 had no Ollama verifier evidence, and AC6's manager-call replay was covered only hermetically, yet both said "Met for …" | **Applied.** Both are now "Partly met" |
| V3 | quality | Important | There was no deviations section | **Applied.** It now covers the fix pauses, the release changes, the worktree reset, the AC10 narrowing, re-warm evidence not saved, the plan step 16 SHA and the receipt-check headroom key |
| V4 | quality | Important | AC9 was incomplete: no final inspect, no receipt digests, and `commands.txt` was only partial | **Applied.** Captured `inspect-final*.json` and `receipt-digests.txt` at review. AC9 is now "Met with gaps", and the gaps are listed |
| V5 | quality | Important | The outcome line contradicted itself about D6 | **Fixed.** D3, D4 and D5 are fixed; D6 and D7 are open |
| V6 | test | Important | AC12's "0 stream_event" count had no evidence file | **Applied.** `evidence/ac12-event-logs.txt` records the size, sha256, stream_event count and result count for both logs |
| V7 | quality | Suggestion | The dates were wrong, and the "no `.flow` reads" claim had no evidence file | **Fixed.** Every timestamp is 2026-09-26, and `evidence/producer-tool-calls.txt` lists every producer tool call |
| V8 | quality | Suggestion | The decision gate could warn when a single-turn grant has an inspect-only rationale | **Added** to the HANDOFF follow-ups |
| V9 | test | Suggestion | `commands.txt` leaves out the preflight, timing and receipt-check commands | **Recorded** as an AC9 gap |

## Requirement fit

- **Primary outcome** (validate the chain live): **partly achieved.**
  - **Proven live:**
    - authority and preparation;
    - real Claude manager and producer turns;
    - an expansion escalation with nothing sent while paused;
    - an engineer decision;
    - a resume replaying the same proposal under a single-use grant;
    - lineage accounting;
    - sealed, valid receipts with expansion evidence;
    - the D1 fix.
  - **Not proven live:** the automatic grant, manager-call replay, the verifier and a completed job.
- **R7 held:** every defect was fixed in its own run (D3, D4, D5), and none inside this one.
- **Rules held:** no staging, and no paid call without a go.

## Validation fit

The evidence is real-provider and ledger-derived, with a verdict for each AC, and every verdict is now worded to match its evidence. Mutation checks don't apply, because no code changed.

## Residual risks

- D6 and D7 are open. Until D7 is fixed, a manager that splits "inspect" from "edit" will fail a v8 job.
- The automatic grant, manager-call replay and the verifier are still unproven live. That's for `v8-live-validation-3`, which needs a new work id.
