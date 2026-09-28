# Acceptance Review: v8-live-validation-3

**Scope:** the run's evidence and write-up (`80edda4`) and the review corrections (`codex/v8-live-validation-3`), judged against `requirements.md` (Changes 1–7, R1–R9), `acceptance-criteria.md` (AC1–AC13) and `plan.md` (binding amendments). The docs change produced by the job is PR #47, which is reviewed here for faithfulness only.

## How the review ran

- **Coordinator:** read the approved definition and plan, and compared every AC verdict with the evidence. Ran the mechanical gates:
  - 0 symlinks committed (`git ls-files -s … | awk '$1=="120000"'`);
  - `validate-orchestration --stage acceptance` is valid;
  - no files outside `.flow` changed on the run branch (no Flow code change, R7).
- **quality-reviewer** (opus): approved. Every AC verdict matches the evidence: call counts, headroom maps, digests, timings, the D4 repair, and the grant and escalation chain. There was no staging and no broken amendment. It had no shell, so the coordinator ran the git checks and reviewed PR #47 (below).
- **test-engineer** (sonnet): approved. Each validation-plan row's evidence contains the claimed fact. It found oracle weaknesses in `receipt_check.py`.
  - Advisory expertise: `no_match` (request `7bfb591c-c0e3-425a-8c44-bc9a78f42acd`), so nothing was delivered.

## Findings and dispositions

| # | Source | Finding | Disposition |
|---|---|---|---|
| T1 | test | The stub scan covered only the receipt. | **Fixed.** It now also scans the ledger events and all 31 attempt files. The only hit is `acceptance.snapshot.md`, which quotes the criterion, and it is excluded. |
| T2 | test | The D1 keys were silently omitted when the event log was missing. | **Fixed.** A missing log now reports "MISSING: check could not run". |
| T3 | test | The D7 ratio could pass vacuously as `0/0`. | **Fixed.** It reports "NO CHECKPOINTS" when there are none, and counts live and quarantined checkpoints separately. |
| T4 / Q | test, quality | "5 sends before the pause" was reconstructed, not asserted. | **Fixed.** The checker asserts 5 sends before the pause, 0 between the pause and the decision, and 1 after, from the ledger event times. My first version of this check returned 0 vacuously, because it read a missing timestamp; that was caught and corrected before recording. |
| T5 / Q | test, quality | AC6 call identity wasn't stated. | **Fixed.** Asserted: the escalated `denied_row_id` `6780598c…` is manager call 6, which completed once, and the automatic grant's `consumed_by` is call 5. |
| Q1 | quality | D7 was checked through checkpoints; the AC wording isn't checkable, because the ledger stores digests only. | **Relabelled** as "met through a substitute". The facts line is in all 13 checkpoints (6 live and 7 quarantined, with base64 decoded). |
| Q2 | quality | AC1 cited the wrong files. | **Fixed:** `shaper-contract.json` for `delegated_expansion`; the charter and inspect outputs for the headroom. |
| Q3 | quality | The baseline file showed rc=0 alongside `failures=2`. | **Noted:** the rc is from the `tail` pipe. |
| Q4 | quality | Orchestration checks before decide and recover weren't recorded, and neither was the re-warm before recover. | **Noted honestly:** they ran but weren't saved. `decide-expansion` validates internally. |
| Q5 | quality | AC13 cited no post-seal `stuck` output. | **Fixed:** `evidence/stuck-after-seal.json` lists nothing for this run. |
| Q6 | quality | The D4 repair added no send, so the escalation stayed at call 6. | **Recorded.** |
| Q7 | quality | The recovery actor defaults to `codex-assisted-recovery` in a Claude-only run. | **Recorded** as an observation, to become a capability gap at archive. |
| Q8 | quality | PR #47 needed checking. | **Checked by the coordinator.** The row follows `inspect-delivery` and precedes the new `stuck` row. The raw `\|` is kept in the TOML, and the escaped form is in both tables; `--check` is clean. The expected generation is clarified as the ledger attempt generation. The refusals now include the held-fence case, and the ceiling wording is corrected. The test file is deliberately not carried over: `test_flow.py:3015` already asserts `--check`. That note is posted on the PR. |
| Q9 | quality | Evidence hygiene: empty lock files, and local environment details in checkpoints. | **Accepted.** The lock files match earlier runs, and Andy is the only user. |

## Review Summary

### Verdict
- Ready to accept.

### Findings
- **Critical:** none.
- **Important:** none open. The checker weaknesses (T1–T5) and the D7 labelling (Q1) are fixed.
- **Suggestions:** dispositioned above. Q7 goes to the archive gap ledger.

### Requirement Fit
- The primary outcome is met: the full v8 chain ran end to end on real providers, sealing a valid `completed` receipt. The secondary docs outcome is also met (PR #47).
- **Firsts, live:**
  - an automatic grant (AC4);
  - a D4 repair;
  - a D5 recover after a grant;
  - a local-verifier `valid_pass`;
  - a completed job.
- R7 holds (no Flow code), R9 held (no Python needed for operations), and nothing was staged.

### Validation Fit
- AC1–AC12 are met, and AC13 is not applicable. D7 is met through a substitute, and D6 was not exercised.
- The evidence is re-recorded with the hardened checker. Every verdict now rests on a file-recorded assertion, except the unsaved pre-recover checks noted in Q4.

### Residual Risks
- D6, and the stuck, abandon and successor path (AC13), are still unproven live.
- One attempt means a single sample of model behaviour.
- The manager conversation text is visible only in checkpoints.
- Codex, replan expansion and multi-attempt lineage remain untested live.
