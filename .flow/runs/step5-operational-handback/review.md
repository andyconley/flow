# Acceptance Review: step5-operational-handback

**Scope:** `be5937b..dfdce82`:
- the seven planned commits;
- the implementation-review refinements `6106762` and `46cefbf` (RS1, which you approved);
- the acceptance fixes `dfdce82`.

Judged against `requirements.md` (revision 2, with your R10 and R9 amendments), `acceptance-criteria.md` (AC1–AC23, AC12b, AC12c), and `plan.md` (I1–I6, D1–D16, A1–A18).

## How the review ran

- **Implementation review, before handback** (`implementation-review.md`): quality, test and security reviewers. All their findings are fixed or dispositioned, except QR17, which is deferred.
- **Acceptance lane:**
  - **test-engineer** (sonnet) verified every regression test added after the implementation review.
    - Verdict: pass. Each test has a concrete input and an observable result that would differ if its fix were reverted.
    - It also confirmed that the amended AC9 matches `conservative_charge`.
    - Advisory expertise was admitted: "Define a test oracle with a concrete example", request `8e49a620-44c2-4648-8612-3210c8da8f7a`. The role applied it (`trigger_satisfied`), and the disposition is recorded. An earlier lookup, `5f5eb7c5-d094-459d-a05f-1b65841a64f5`, was never delivered to a role; its payload was not captured, so the lookup was repeated.
  - **quality-reviewer** (opus) confirmed every Fixed disposition is present in the code, and judged requirement fit.
    - Verdict: needs refinement, with three Important findings (AQ1–AQ3) and eight Suggestions.
    - The findings were wrong failures (never false passes) and inconsistent run records. All are handled below.
- **Coordinator:**
  - Ran `validate-orchestration --stage acceptance`: valid.
  - Ran the full suite after the acceptance fixes: 1,771 OK, 0 skipped.
  - Re-ran all 14 mutation checks: all caught.
  - Checked the AQ2 claim against the ledger guards.

## Acceptance findings and dispositions

| # | Sev | Disposition |
|---|---|---|
| AQ1 | Important | **Fixed.** V6 checks a pre-release predecessor's digest link and ledger charge but doesn't recurse into it (P9). An informational item records this. Test: `PreReleasePredecessorTests`. |
| AQ2 | Important | **Rejected, with evidence.** The claim was that V17 replays final charges where the gate saw U for an in-flight row. That can't happen. Every grant path refuses while any row of the same attempt is `started` or `unknown`: `decide` and `decide_manager_call` check `_unresolved_action`, which covers actions and manager calls (`execution_ledger.py`); both regrants and both reissues check it too. So at every grant, every earlier send in the attempt is final, and predecessor rows are terminal. Concurrent grants (AC12c) are allowed-but-unsent rows, charged 0 by both the gate and the replay. The replay therefore sees exactly the gate's charges, which was the plan's F2 argument. |
| AQ3 | Important | **Fixed.** `HANDOFF.md` lists `46cefbf` and the acceptance commit, and the stale "Andy decides RS1" step is removed. `implementation-review.md` names both refinement commits and 14 mutations. |
| AQ4 | Suggestion | **Fixed.** The pre-release branch treats an unreadable `envelope.json` as absent, so the result is `unsupported_receipt` with exit 2, not a crash. |
| AQ5 | Suggestion | **Fixed.** trace counts unobserved sends by the receipt's rule, including rows whose usage was not recognised. ADR 0020 and `HANDOFF.md` say every row charged conservatively counts in `unrecognised_usage` and as an unobserved send. |
| AQ6 | Suggestion | **Fixed.** P2 in `requirements.md` and F3 in `definition-dispositions.md` carry the RS1 amendment marker. |
| AQ7 | Suggestion | **Fixed.** ADR 0020 says a reissue denial denies the row (`grant_changed op=deny`, `grant_id` cleared). |
| AQ8 | Suggestion | **Fixed.** The dead V10 check is removed. An unsafe receipt is reported with its reason, not as missing. |
| AQ9 | Suggestion | **Fixed.** Recursive predecessor verification is memoised per attempt. |
| AQ10 | Suggestion | **Fixed.** The `__main__` block in `test_token_charge.py` is moved to the end of the file. |
| AQ11 | Suggestion | **Fixed.** `finish_attempt` refuses to seal a v8 attempt as `denied`. Test: `test_a_v8_attempt_never_seals_denied`. |
| AT1 | Info | **Agreed.** Two charge-table rows pin the no-readable-counter boundary and don't separate RS1 on their own. Two other rows do. |

## Review Summary

### Verdict
- **Ready to accept.**

### Findings
- **Critical:** none.
- **Important:** AQ1 and AQ3 are fixed. AQ2 is rejected with evidence.
- **Suggestions:** AQ4–AQ11 are fixed. QR17 (performance) is deferred, as recorded in `implementation-review.md`.

### Requirement Fit
- **R1–R17 are met,** including both amendments:
  - R10/AC10: zero token headroom pauses for a decision.
  - R9/AC9: unrecognised usage is charged conservatively.
- **Confirmed by the acceptance quality review:**
  - the token gate on every paid path;
  - hard versus expandable;
  - the reissue checks;
  - the full-row seals under `send_lock`;
  - request files written before consume;
  - V1–V17 with the R14 requiredness table;
  - pre-release attempts, which are readable and abandonable but refuse to advance;
  - ADR 0020 matching the final code.
- **No scope drift.** The non-goals hold:
  - no MCP handback;
  - no `traceparent`;
  - no dollar costs;
  - no job-charter digest or symlink hygiene.

### Validation Fit
- **Suite:** 1,771 OK, 0 skipped, with `FLOW_MAF_PYTHON`. Help is up to date.
- **Acceptance criteria:** every AC maps to named tests with falsifiable oracles (`validation-results.md`).
- **AC16:** exact failing sets, with two documented and justified deviations.
- **Mutations:** 14, all caught.
- **Stock runner:** one lineage runs through the pinned stock Magentic runner and verifies cleanly.
- **Real data:**
  - trace reads `v8-live-validation-3`, and marks it `unsupported_contract`;
  - verify-receipt refuses it as `unsupported_receipt` (exit 2);
  - the run tree was unchanged.
- **Honestly limited:**
  - providers are stubs;
  - the Codex manager identity is proven at the contract level only.

### Residual Risks
- **RS2 / R12:** grants that are allowed but not yet consumed reserve no tokens. This is the concurrent overshoot bound you chose, and it is documented.
- **No live run yet.** Nothing has run live under a v4 charter; `v8-live-validation-4` should exercise trace, the cap and verify-receipt with real providers.
- **Unreadable usage:** a usage block with no readable counter still charges exactly the sealed amount. It is reported as unrecognised.
- **QR17:** the lineage charge is computed twice per action decision.
- **Sealed records:** this run's sealed Delivery Charter records the definition bytes from before the two amendments, as `definition-dispositions.md` documents.
