# Plan Review: business-analyst

Role: business-analyst. Reviews `plan.md` (draft) against `requirements.md` and `acceptance-criteria.md`, both approved, and `solution.md`, accepted. Claim tags: observed, inferred, recommended, unverified.

## AC-to-chunk/commit/test trace table

| AC | Chunk | Commit(s) | Named test(s) | Status |
|---|---|---|---|---|
| AC1 | 1 | `plan.md:156` (commit 10) | `plan-validation.md:15-23` (tests 1-4) | traced (observed) |
| AC2 | 1 | `plan.md:157` (commit 11) | `plan-validation.md:27-35` (tests 5-7) | traced (observed) |
| AC3 | 1 | `plan.md:154`, `:157` (commits 8, 11) | `plan-validation.md:39-41` (test 8) | traced but weak — see Important #2 |
| AC4(b) | 1 | commits 4, 7, 8, 11 | test 9 | traced |
| AC4(d) | 1 | commits 5, 6, 11 | test 10 | traced |
| AC4(f) | 1 | commit 11 | test 11 | traced |
| AC4(g) | 1 | commit 11 | test 12 | traced |
| AC4(h) | 1 | commit 11 | test 13 | traced |
| AC4(i) | 1 | commits 5, 8, 11 | test 14 | traced |
| AC4 clean-transport | 1 | commit 11 | test 15 | traced |
| AC4(a),(c),(e) | 2 | none (component list only, `plan.md:96-102`) | none named | disclosed gap — see Important #1 |
| AC5 | 2 | none | none named | disclosed gap — see Important #1 |
| AC6 | 1 | commits 5, 6, 11 | tests 16-17 | traced |
| AC7 | 1 | commit 6, 11 | test 18 | traced |
| AC8 (unsent-grant re-grant, chunk1) | 1 | commit 7, 8, 11, 12 | tests 19-20 | traced |
| AC8 (no-dispatch re-grant, boundaries a/c/e) | 2 | none | none named | disclosed gap — see Important #1 |
| AC9 | 1 | commits 10 (refusal codes), 12 (superseded seal, lead guard) | tests 21-24 | traced but split across two commits with no explicit sub-clause-to-commit mapping — see Important #3 |
| AC10 (generation, marker subtests) | 1 | commit 6, 9 | tests 25-26 | traced |
| AC10 (added/removed-resolution subtests) | 2 | none | none named (`plan-validation.md:112` heading itself defers these) | disclosed gap — see Important #1 |
| AC10 (v7 unchanged) | 1 (regression) | — | test 27 (reused existing test) | traced |
| AC11 | 1 | commit 13 (14 in commit list — "inspect") | test 28 | traced |
| AC12 (test-runner zero-calls, chunk1) | 1 | commit 15 | test 16's assertion + test 29 (manual mutation exercise, not a standing unittest) | traced with caveat — see Suggestion #1 |
| AC12 (worker-adapter zero-calls, chunk2) | 2 | none | reserved name only (`plan-validation.md:150`) | disclosed gap — see Important #1 |

## Findings

### Important #1 — Chunk 2 AC coverage exists only as a component list, not a plan
- Evidence: `plan.md:94-102` (chunk-2 scope) contains no commit sequence, no named tests, and states "Chunk 2 is re-planned at file level after chunk 1 merges" (`plan.md:102`). This affects AC4(a)/(c)/(e), AC5, part of AC8, part of AC10, and part of AC12 — five of twelve criteria have no chunk/commit/test trace yet.
- This is *disclosed*, not silent (the plan says so explicitly, and requirements.md's own delivery-order decision D1 sanctions splitting into two chunks). But the brief asks to trace every AC to a chunk, commit, and named test, and five criteria cannot be so traced against this document. If the engineer accepts this plan as covering "the definition," they should accept it knowing chunk 2 is present only as a scope list, not a verifiable plan.
- Disposition (recommended): accept as-is only if the acceptance gate is explicitly "chunk 1 plan accepted; chunk 2 plan to follow before its own PR," not "this plan, in full, accepted." Otherwise require a chunk-2 commit/test sketch before sign-off.

### Important #2 — AC3's test is a proxy, not a direct ordering assertion
- Evidence: `plan-validation.md:39-41` (test 8) — the plan's own validation note admits: "assert on the final call counts as a proxy" because there is no clean mid-flight hook to prove zero-calls-before-grant directly, absent a test-only seam.
- AC3 text (`acceptance-criteria.md:14`): "The worker and manager adapter call counts stay at zero until the ledger authorizes a call" — this is an ordering claim, and the validation plan concedes it is only proven by final counts, not by an ordering assertion against ledger events.
- Disposition (recommended): either add the test-only hook the validation note gestures at (ledger `seq` vs. adapter-call order comparison, `plan-validation.md:41`), or explicitly note in `plan.md` that AC3 is proven by absence-of-call-count rather than by causal ordering, so the acceptance criterion's "until" wording is not overclaimed.

### Important #3 — AC9's four sub-clauses are split across commits 10 and 12 without an explicit map
- Evidence: `acceptance-criteria.md:35-39` lists four AC9 sub-clauses: (1) refusal once generation inactive, (2) old attempt sealed superseded after explicit resume/supersede, (3) function-seam refusal while any action is `unknown`, (4) abandonment still succeeds while `unknown`. `plan.md:35-44` (commit-1-equivalent scope item 1) lists the refusal code `lead_generation_inactive` under version-routing refusals (item 1, no commit number attached directly, though item 1 maps to commit 10 by content). `plan.md:158` (commit 12) is explicitly tagged "(AC9)" but only covers the superseded-seal and lead-guard sub-clauses.
- Test 21 (stale-generation refusal, `plan-validation.md:99-101`) is not attributed to a specific commit in `plan.md`'s commit sequence; it could plausibly land in either commit 10 or commit 12.
- Disposition (recommended): plan.md should state explicitly which commit introduces the `lead_generation_inactive` refusal path (commit 10, by content, but currently only commit 12 is AC9-tagged), so a reviewer checking "AC9 done" against a specific commit does not have to infer it.

### Important #4 — No refusal reason for "recovery invoked on an actively running (non-interrupted) v8 attempt"
- Evidence: the stable refusal codes at `plan.md:36-43` cover version mismatches, terminal state, generation staleness, in-progress recovery, reconciliation, checkpoint problems, drift, and lineage conflicts. None of them is named for the case where the operator runs `recover-delivery-lead` against a v8 attempt that is `started` with **no** interruption row (i.e., still actively executing, not crashed).
- Requirement 2 (`requirements.md:41-44`) and AC2 (`acceptance-criteria.md:13`) establish that recovery must be explicit and exclusive, but neither the requirements nor the plan states what happens if the operator invokes it against a healthy, running attempt. `reconciliation_required` or `no_restorable_checkpoint` might incidentally fire, but neither is named for this case, and inferring which code applies is exactly the ambiguity AC2/AC11 are meant to prevent.
- Disposition (recommended): plan.md should either name an explicit refusal code for "attempt is not interrupted" or state that this case is out of scope because the CLI itself gates on interruption state before calling into recovery (in which case that gating should be named in the Contracts section, not left implicit).

### Suggestion #1 — AC12's chunk-1 mutation check is a documented manual exercise, not a repository artifact
- Evidence: `plan.md:161` (commit 15): "Mutation evidence, recorded in `validation-results.md`, with no repository file." `plan-validation.md:130-131, 144-147` confirm the mechanism is "a one-time manual or CI-scripted mutation exercise... not a permanent unittest."
- AC12 (`acceptance-criteria.md:48-50`) requires the two named assertions to "each fail when their guard is removed, and each is shown to do so by a mutation check." The underlying assertion (test 16) is a standing unittest; the mutation-removal-and-restore step that proves it is load-bearing is manual and produces no committed artifact beyond a results note.
- Disposition (recommended, low risk): acceptable given the project's dependency-free stance (no `mutmut`/`cosmic-ray`), but the plan should say explicitly where `validation-results.md` lives and that it is retained as run evidence, so the mutation check has a durable record rather than being a one-time terminal-session action that leaves no trace after this run closes.

## Requirement-change check

- The requirements.md assumption "No runtime work is needed" is explicitly and visibly amended by plan.md item 5 (`plan.md:57`) with an inline note and decision P1 (`plan.md:195`). This is a disclosed change, not a silent one — no finding needed here.
- The four "new" risks (R8, R9, and the two decisions folded into Owned Risks, `plan.md:210-214`) are explicitly labeled "New" in the Owned Risks section — also disclosed, not silent.
- No other requirement text was found altered without a corresponding call-out in plan.md's own prose (inferred from a line-by-line comparison of requirements.md Reqs 1-12 against plan.md's Scope and Contracts sections).

## Operator-facing states and refusal reasons

- The `started` + interruption row state is described as "interrupted, recoverable or blocked" (`plan.md:118`) as a single ledger state covering two operator-visible conditions. This is disambiguated downstream by `inspect-delivery`'s `recoverable:`/`blocking:` output fields (`plan.md:91`), so it is not ambiguous in practice — no finding, but noted as the resolving mechanism a reviewer should check for when this plan is implemented.
- See Important #4 above for the one gap found in the refusal-reason set.

## Summary

Ten of twelve ACs trace cleanly to a chunk 1 commit and named test; the remaining five sub-criteria (AC4 a/c/e, AC5, part of AC8, part of AC10, part of AC12) exist only as chunk-2 scope prose with no commit or test, which the plan discloses but a strict trace cannot close. AC3's test is conceded by the plan's own validation note to be a proxy rather than a direct ordering proof. AC9 is split across two commits without an explicit sub-clause map. One operator-facing gap: no named refusal reason for invoking recovery on a non-interrupted, actively running attempt. The "no runtime work" assumption change and the four new risks are disclosed, not silent — no finding required there.

Path: `/Users/andyconley/.codex/worktrees/delivery-recovery/flow/.flow/runs/chartered-delivery-recovery/research/plan-review-ba.md`
