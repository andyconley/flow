# Handback: step5-cancellation

Step 5 slice 1 of MAF adoption: cancelling and abandoning chartered v8 attempts (ADR 0019).

**Branch:** `codex/step5-cancellation`, six commits on top of the plan commit `62a4d5f`:

| Commit | Content |
|---|---|
| `5bf826b` | `feat(ledger)`: seal cancelled and abandoned attempts with their uncertainty |
| `0973be1` | `feat(delivery)`: record process identity for every dispatching parent |
| `1632044` | `feat(delivery)`: abandon stuck attempts; add the lead CLI and the stuck scan |
| `1050db2` | `feat(delivery)`: cancel a live attempt cooperatively |
| `ac3aa4c` | `docs(delivery)`: ADR 0019 and step 5 cancellation |
| `b066309` | `fix(delivery)`: harden cancel and abandon after review |

Nothing is pushed.

## What shipped

- **New terminal statuses `cancelled` and `abandoned`.** Each is sealed by one ledger transaction that:
  - releases unconsumed grants and closes open expansions;
  - renders the receipt from its own snapshot, checks it against the ledger, and writes it;
  - bumps the owner generation.

  Uncertain rows stay uncertain. The v8 validator allows them only under these two statuses, with `termination` and `evidence_damage`.
- **ADR 0016 amended.** Those two statuses no longer block a lead change. A v7 attempt sealed `unknown`, and any started attempt, still do. Recovery refuses both statuses, and successors list them as predecessors, counting their uncertain spend.
- **Process identity.** Each dispatching parent (a live run, or a restart/pending/answer recovery) writes `control-g<N>.json` with its pid, a timezone-independent start time, a hashed machine id, and `cancel_supported`. Flow's adapters register the MAF, provider and test groups. The targeted test runs in its own session, and the MAF launcher kills its whole group.
- **CLI:**
  - `flow run cancel-delivery`: cooperative SIGTERM; seals `cancelled`, or reports `attempt_finished`.
  - `flow run abandon-delivery`: reaps recorded groups by identity, then seals `abandoned`.
  - `flow run delivery-lead`: the four lead actions, with stable codes.
  - `flow run stuck`: read-only; every started attempt with its next command.
  - `inspect-delivery` shows the attempt status apart from the expansion status, the stopper, damage, control records and the next command.

## Proof

- **Full suite:** 1,638 tests OK, 0 skipped at `b066309`, and green after every commit.
- **Mutations:** M1–M6 each fail their named acceptance-criterion tests, re-run at `b066309`. See `validation-results.md`, which also maps every acceptance criterion and amendment to its test and oracle.
- **Reviews:** quality, test and security reviews ran, and every finding is dispositioned in `implementation-review.md`. There were no critical findings; all important findings are fixed.

## Per-check verdicts

- **Process identity, signals and reaping:** validated on macOS against the change itself.
- **The Linux `/proc` start-time reader:** parser-tested only.
- **pidfd signalling:** not exercised.
- **Real Codex, Claude and Ollama:** not exercised; fakes and stubs only. `v8-live-validation-3` covers them, and it is paid and needs Andy's go.

## Risks and residuals (ADR 0019)

- A microsecond window on macOS: a parent that finishes between the closed-marker check and the signal can be terminated after it has sealed.
- A seal-time ledger generation mismatch records no interruption; the next recovery claim records `unmarked_process_exit`.
- Leader-gone reaping can hit orphaned members of a reused pgid owned by the same user (R4 accepts this).
- `--actor` is attribution only. Cancel and abandon are fenced on the owner generation the operator saw.

## Follow-ups

- Have `change_lead_claim` return stable codes instead of prose (the CLI maps prose today).
- Optional stronger reaping evidence: mirror each group registration in the ledger.
- The real project has a stuck attempt: `flow run stuck` lists `v8-live-validation` `f628faa9…` with next command `abandon-delivery … --expected-generation 1`. It was left untouched, pending Andy's decision.
- The remaining step 5 slices (trace correlation, receipt verification, MCP handback, token cap), then `v8-live-validation-3`.

## Next

`/flow-review step5-cancellation`
