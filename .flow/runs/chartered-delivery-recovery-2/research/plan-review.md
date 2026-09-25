# Plan review: chunk 2

- **Reviewers:**
  - `plan-review-requirements` (business-analyst; advisory request `3e5c5829…`, `no_match`);
  - `plan-review-product` (product-manager).

  Both were read-only and ran concurrently.
- **Verdicts:** both reviewers returned "needs changes". There were no design flaws: every finding concerned document integrity or commit sequencing. All are dispositioned below.

| Finding | Disposition |
|---|---|
| **BA critical:** `acceptance-criteria.md` still carried manager-call resolution (item 4) and manager receipt subtests (item 8), contradicting the amendment. | **Fixed.** `acceptance-criteria.md` is rewritten to the amended scope. AC4 is marked removed, and AC8 covers actions only. |
| **BA critical:** "AC12" meant both the parent's suite and mutation check and the new worktree guard. | **Fixed.** This run numbers AC1–AC12 itself (AC11 is the suite and mutation checks, AC12 the worktree guard), and parent criteria are cited as "parent ACn". `requirements.md` and `validation-plan.md` are aligned. |
| **BA important:** the abandon-only operator action was not named in the plan. | **Fixed.** `plan.md` and `acceptance-criteria.md` name the existing, unchanged `release` (or the lifecycle `block`). |
| **BA suggestion:** requirement 3's text is dead. | **Fixed.** It is marked dropped, and the text is kept for the record. |
| **PM critical:** commit 4's route-side worktree guard needs `_resolve_chartered`, which arrives later, breaking "green after each commit". | **Fixed.** Commit 4 is the prepare side only. The route side and its subtest land with the route (now commit 10). `validation-plan.md` splits the AC12 test. |
| **PM important:** commit 8 bundled the binding check with the inspection text. | **Fixed.** It is split into commit 8 (binding) and commit 9 (inspection and the refusal pointer). There are now 12 code and doc commits. |
| **PM suggestion:** the risk numbering diverged from `solution.md`. | **Fixed.** `plan.md` cross-references R4 and R5 as requirement-level risks. |
| **PM suggestion:** commit 5 is a test, not a guard. | **Fixed.** A note in the group header says so. |
