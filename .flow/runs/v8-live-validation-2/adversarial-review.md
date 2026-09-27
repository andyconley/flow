# Adversarial Review: v8-live-validation-2 (definition)

- **Reviewers:** three read-only reviewers, run concurrently, 2026-09-26:
  - `adversarial-product` (product-manager);
  - `adversarial-requirements` (business-analyst; the expertise lookup returned `no_match`);
  - `adversarial-architecture` (solution-architect, the independent verifier).
- **Brief:** `briefs/adversarial-review.md`.
- **Check by the coordinator:** the architecture reviewer's C1 was checked against `cli/delivery_gateway.py:1581-1583` and `:1628-1638`.

## Dispositions

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| C1 | architecture | Critical | Any provider call that raises before its completion is observed, including an adapter timeout (manager 120 s, producer 300 s, Ollama 60 s), is marked `unknown`, and the attempt can't be resumed. AC8 wrongly called a timeout environmental and resumable | **AC changed.** AC8 gains an "uncertain send" outcome: release, the work id is blocked, and no second attempt. Preflight adds a timed verifier call with a diff-sized prompt, as a go/no-go gate against 60 s. Requirements Change 5 is updated to match |
| BA1 | requirements | Critical | AC8 B2 and R6 assumed an unsealed attempt could be resumed or superseded, which is false after an uncertain send | **AC changed.** Same fix as C1. AC10 notes that an uncertain-send attempt is the last one |
| I1 | architecture | Important | The limits and headroom produce both events: call 5 is granted automatically and call 6 escalates, with a peak of round 3, under the ceiling of 6 | **Assumption A3 confirmed** |
| I2 | architecture | Important | The 600 s launch deadline is checked only on protocol reads and writes, so a call in progress finishes and the next step records a resumable transport interruption. The first run measured manager calls at 21.0, 9.2 and 12.2 s, and the edit had run 94 s when cut off. Estimated first launch: 250 to 430 s | **Open question closed.** The mechanism is recorded in Change 5 |
| I3 | architecture | Important | Per-call timings are already in the ledger `events` table, with microsecond timestamps, but `inspect-delivery` doesn't project them. The first run's "not captured" claim was wrong | **Requirement changed.** Change 4 names the `ExecutionLedger(...).snapshot()` extraction and backfills the first run's timings. AC9 is updated |
| I4 | architecture | Important | The charter's wording could lead the producer to write a backslash-escaped pipe in the `flow.toml` invocation, which isn't valid TOML | **Charter changed.** `flow.toml` keeps the raw pipe; only the generated rows use the backslash-escaped pipe |
| I5 | architecture | Important | The job test's docstring rule 2 forbids the backslash-escaped pipe and must be inverted. The test code doesn't change | **Requirement changed** (Change 1) |
| BA2 | requirements | Important | An environmental verdict needed distinguishing evidence | **AC changed.** AC8 records the specific error signature |
| BA3 | requirements | Important | Removing the first run's worktree wasn't verified | **AC changed.** AC2 and the preflight record a fresh, clean worktree |
| P1 | product | Important | Two of the first run's gaps (`manifest-timeout-enforcement`, `handback-unreached-assignment-outputs`) were neither addressed nor excluded | **Requirement changed.** A new "Known risks carried" section, and R2 states the effective fixed caps |
| P2 | product | Important | The worst-case manager-call budget didn't reconcile with the single sealed unit of headroom | **Requirement changed.** The budget line points to R4's escalation path |
| BA4 | requirements | Suggestion | AC12 should also confirm that partial messages were absent, and relate the stream size to the old cap | **AC changed** |
| S1 | architecture | Suggestion | The manifest's `timeout_seconds` and `max_output_chars` are ignored | **Folded into R2** |
| S2 | architecture | Suggestion | approve-definition, start-plan and prepare should pass | **A1 and A2 confirmed.** The digest check is kept after installing v0.36.1 |
| P3 | product | Suggestion | A2 and the `job-charter-sealed-digest` gap were the same item | **Merged** (A2 cites the key) |
| BA5, BA6 | requirements | Suggestion | The timing question was correctly left open, and A3 is consistent | **Confirmed.** The timing question is now closed by I3 |

No findings were rejected, and the reviewers raised no contested claims.
