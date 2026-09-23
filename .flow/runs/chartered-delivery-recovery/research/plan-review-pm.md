# Plan Review: Product (scope, slicing, engineer decisions P1-P5)

Role: product-manager. Date: 2026-09-23. Reviewed against `requirements.md` (approved), `acceptance-criteria.md` (approved), `solution.md` (accepted), `plan.md` (draft), `research/plan-validation.md`.

Claim tags: **observed**, **inferred**, **recommended**, **unverified**.

## Critical

1. **P5: chunk 1 as one 15-commit PR is oversized for safe review and bisection; split into 1a/1b as the plan itself proposes.**
   - Evidence: `plan.md:143-161` (commits 1-15), `plan.md:199` (P5 question). Commits 1-9 build the mechanism (ledger, refactor, interruption, seal seam, contracts, recovery core, claim, runtime restore); commits 10-11 wire routing and the AC1-AC8 matrix; commits 12-14 add lead-guard/superseded-seal/lineage/inspection, which are functionally independent of the recovery path itself (they gate lead *ownership changes*, not recovery *mechanics*).
   - Disposition (**recommended**): split as the plan names — **1a = commits 1-11** (recovery mechanism plus AC1-AC8), **1b = commits 12-14** (lead guard, superseded seal, lineage, inspection/AC9, AC11), each an independently shippable, honestly-stated PR. Commit 15 (mutation evidence) rides with whichever PR completes AC12's test-runner check (1a). This halves blast radius per review pass and lets 1a merge and de-risk the harder concurrency/evidence-reuse work before 1b's lead-authority change lands. Recommend against 15-in-one: a single PR this size makes `git bisect` and reviewer attention span a bigger risk than the two-PR seam cost.

2. **Lineage limit-counting (plan item 12, decision P2) is scoped into chunk 1 without a named acceptance test; it is deferrable to chunk 2 or a follow-up without breaking AC1-AC12.**
   - Evidence: `research/plan-validation.md` §1 lists AC1-AC12 to test mappings; only AC9's test 22 (`test_lead_resume_or_supersede_seals_the_old_attempt_as_superseded`) touches `predecessors`, and only to assert the envelope link exists — no test in that map exercises `lineage_usage` counting predecessors' paid/verifier spend against the charter cap (**observed**, absence in section 1). `plan.md:83-87` (item 12) and `solution.md:107` (design item 10, "engineer: yes") are the only sources of this requirement; it answers risk R4, not an AC.
   - Disposition (**recommended**): keep it in scope since the engineer already said yes at solution time (design item 10) and R4 depends on it, but flag explicitly in the plan that no acceptance criterion tests it — the only test evidence is R4's closure, not AC1-12. If chunk 1 needs to shrink for P5, lineage-usage counting (item 12) is the safest candidate to push into 1b or a fast-follow, because no AC regresses without it; only R4 (budget-reset abuse) stays open a little longer, and it's already gated behind an explicit lead-change action, not silent.

## Important

3. **Chunk 1 to chunk 2 boundary is shippable and honestly stated — confirm this, don't just assume it.**
   - Evidence: `solution.md:134` ("Until chunk 2 lands, v8 uncertain sends stay interrupted, blocked, and visible, and abandonment remains possible") and `plan.md`'s Scope/Out-of-scope sections mirror this. AC11 (inspection) ships in chunk 1, so an operator can see a boundary-(a)/(c)/(e) attempt as blocked with a stated evidence need, not as a silent stall.
   - Disposition (**observed**, confirms plan is correctly honest): no change needed. This is the one scope-boundary check that passes cleanly — call it out as a strength, not a gap, so the engineer doesn't second-guess it during review.

4. **P1 (runtime `pending` restore mode) — recommend accept into chunk 1, but log the requirements deviation explicitly rather than let the plan's parenthetical carry it.**
   - Evidence: `plan.md:57` flags this contradicts requirements.md's assumption "No runtime work is needed" (`requirements.md:109`, observed assumption). Dropping boundary (b) from chunk 1 would remove one of the seven kill-boundary tests AC4 requires for chunk 1 (`acceptance-criteria.md:17-23`), directly shrinking AC4's chunk-1 matrix and Requirement 7's list of evidence-free boundaries (`requirements.md:57-62`, "an unconsumed grant" is explicitly named).
   - Disposition (**recommended**): accept the runtime change into chunk 1 — dropping it breaks an explicit requirement bullet, not just a nice-to-have. But since it revises an approved-requirements assumption, this should be surfaced as a formal requirements amendment note (one line, cross-referenced to ADR 0016) rather than only living in the plan's decision list, so a later reader of `requirements.md` doesn't trust a since-superseded assumption.

5. **P3 (refuse `resolve-execution` for v8 now) — recommend yes, and this is nearly free scope, not a deferral candidate.**
   - Evidence: `plan.md:98` (R5, "accepts v8 only by accident"), `solution.md:145` (R5 owner lead-developer, "verify it in chunk 2, and add a v8 route if it is missing"). An explicit refusal is a small, isolated guard (likely one conditional plus one test) versus the risk of an accidental, unreviewed v8 continuation path being reachable before chunk 2's resolution-binding checks exist.
   - Disposition (**recommended**): yes, refuse explicitly now. Low cost, closes a real gap (an accidental permissive route around AC5's resolution-binding requirement, `acceptance-criteria.md:28-31`), and needs no new test infrastructure beyond one refusal test similar to the AC1 pattern.

6. **P4 (checkpoint quarantine directory vs. exclude list) — recommend quarantine, and note it is more work than the alternative but buys real audit value.**
   - Evidence: `plan.md:56` ("Checkpoint files the ledger has not bound are moved to `checkpoints-quarantine/<recovery_id>/`, and their digests are recorded"), tied to R1's fail-closed resolution (`plan.md:203`).
   - Disposition (**recommended**): quarantine over exclude-list. An exclude list only prevents reuse; quarantine additionally preserves the artifact and its digest for later audit or a future replay-safety spike, at the cost of one directory-move operation per recovery. Given R1 explicitly leaves the door open to revisit safe replay "if MAF prompt determinism is proven" (`plan.md:106`), the quarantined files are the evidence a future spike would need — don't discard that for a marginally simpler exclude list.

## Suggestion

7. **Chunk 1's item 5 (runtime pending restore) is MAF-gated and skips in CI (new R9); the plan already discloses this, but the disclosure should be load-bearing at merge time, not just in `plan.md`.**
   - Evidence: `plan.md:211-214` (new R9, local interpreter present, CI has no MAF job, "Validation must therefore run them locally and record that they ran, not that they were skipped").
   - Disposition (**recommended**): treat "record that they ran" as a hard merge gate for chunk 1 / 1a specifically (a pasted local-run log or equivalent in the PR description), not an optional validation note — since this is the one AC4 boundary (b) test that CI cannot itself prove, a merge without that record would silently ship an untested boundary in a PR whose whole premise is a fully-tested kill-boundary matrix.

8. **Minimum useful slice, if further descoped were ever needed:** 1a alone (commits 1-11, AC1-AC8) is the smallest chunk-1 slice that satisfies Requirement 7's "chunk 1 alone lets a paused or crashed attempt resume... from every evidence-free boundary" (`requirements.md:84`). Items 10-13 (lead guard, superseded seal, lineage, inspection) support AC9 and AC11, which are real approved criteria and should ship before chunk 1 is called "done," but they are not required for the requirements' own definition of what chunk 1 alone must deliver. This reinforces finding 1's P5 split rather than adding new scope debate.

## Summary of P1-P5 recommendations

- **P1:** accept into chunk 1 (dropping it breaks Requirement 7 boundary (b)); log as a formal requirements amendment.
- **P2:** keep no-lineage-budget-for-manager-calls (plan's own recommendation); the wider lineage-usage counting (item 12) has no direct AC test and is the best candidate to trim if chunk 1 needs to shrink further than the 1a/1b split.
- **P3:** refuse `resolve-execution` for v8 explicitly now — cheap, closes a real gap.
- **P4:** quarantine, not exclude-list — preserves audit/replay evidence for a future R1 revisit.
- **P5:** split into 1a (commits 1-11) and 1b (commits 12-14); do not ship 15 commits as one PR.
