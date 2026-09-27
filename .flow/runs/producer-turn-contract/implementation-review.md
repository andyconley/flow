# Implementation Review: producer-turn-contract

Scope reviewed: commits `29c9c6a`, `91e567b`, `fdb112b` and `46dbe23`, on top of `fd4954b`.

## Roles

- **quality-reviewer** (opus). Verdict: ready once `validation-results.md` is written. No critical findings.
- **test-engineer** (sonnet). Expertise lookup returned `no_match` (request `d0ef4925-7fc2-48bf-ac69-23af14c8905f`), so no advisory block was attached. Verdict: AC1–AC4 each have a test that fails on the recorded mutations, and there are no vacuous assertions.

## Findings and dispositions

| # | Source | Finding | Disposition |
|---|---|---|---|
| Q1 | quality | `validation-results.md` is missing. | **Fixed.** It is written, and records the suite, the mutations and the AC7 scan. |
| Q2 | quality | The AC1 test does not assert the "complete edit in the same turn" clause. | **Fixed** in `46dbe23`. The phrase is now asserted for v6, v7 and v8. |
| Q3 | quality | The 1,500-byte cap is tested without predecessors. | **Accepted.** The predecessor lines are pre-existing and outside this AC. |
| Q4 | quality | Confirm the AC2 literal against `fd4954b`. | **Verified.** A textual diff of the old inline block against the helper differs only in a lone `+` continuation line, and the string tokens are identical. |
| Q5 | quality | A mode-only change reaches the (c) branch by inspection but has no test. | **Accepted.** AC3 does not require that test, and the branch is exercised by the declared_regression case. |
| T2 | test | The AC2b test asserts only one substring. | **Accepted.** AC2b proves the line reaches the manager task. The full phrase set is pinned by the unit test for AC1, and M1 fails both. |
| T3 | test | The mutation proof is manual. | **Fixed.** The exact mutation edits are recorded in `validation-results.md`, so they can be replayed. |
| T4 | test | The empty/oversized-diff branch and the "recorded diff changed" branch are untested. | **Out of scope.** Both branches predate this change and are not touched by it. |

AC2 note: the protocol-5 byte-identity check is its own test method (`test_protocol_5_facts_are_unchanged`) in `ExecutionFactsTests`, next to the chartered parameterized test, rather than a subtest of it. The assertion is the one AC2 asks for.
