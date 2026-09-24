# Handoff: Chartered v8 Delivery Recovery, chunk 1b

- **Status:** implemented, reviewed, and validated; ready for acceptance review (`flow-review`).
- **Run:** `chartered-delivery-recovery-1b`, a linked follow-on of the archived `chartered-delivery-recovery` (1a, PR #26).
- **Branch:** `codex/chartered-delivery-recovery-1b` off `main` `7b2b7ff`. Worktree: `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`. Not pushed.
- **Decisions:** E1–E5 in `requirements.md`.

## What shipped

- **Lead change fences the old attempt (AC9.2).** A Delivery Lead `resume` or `supersede` seals every started v8 attempt at or below the outgoing generation as `superseded`, before the claim changes. The seal releases unconsumed action grants and bumps the attempt's owner generation, so the ledger fences its grants too. v5–v7 attempts are untouched.
- **Ledger-backed lead guard (AC9.3).** The inert `pending_unknown_actions` check is replaced. A lead change refuses:
  - with `reconciliation_required` on any started or unknown action or manager call in the run's ledger, v7 included;
  - with `lead_guard_ledger_unreadable` on an unreadable ledger, a symlinked ledger, or a missing ledger when attempt directories exist;
  - with `attempt_running` while a live run holds an attempt's `recovery_lock`;
  - with `recovery_in_progress` if the ledger moved between the probe and the seal.
- **Abandonment stays open (AC9.4).** `release` and lifecycle `block` work while sends are unknown.
- **Successor lineage.** A new v8 attempt's envelope lists every earlier v8 attempt as `predecessors`, only when non-empty. `create_attempt` requires an exact match inside its transaction. A started sibling refuses `sibling_attempt_not_terminal`, and prepare creates the attempt under the authority guard. A predecessor may share the successor's lead generation (E4). The task facts name each predecessor.
- **Lineage limits.** Predecessor paid worker sends and verifier sends count against the charter caps in `decide` and the recovery regrant. The retry rule and `max_manager_calls` stay per attempt. The receipt carries `lineage_usage`, which is validated for shape, for the caps, and for agreement with `retry_eligible`.
- **ADR 0016** amendment corrected to match.

Commits:

- `3db384d` run setup
- `34d4354` ADR
- `c67d18f` seal and guard
- `15e15b4` lineage
- `d21a2d2` guard test with no v8 attempt to seal
- `e16e8bd` review fixes

The 1a archive is `79cbffb`.

## Proof

See `validation-results.md`:

- the full suite ran **1442 tests OK, 0 skipped** (baseline 1426);
- the MAF-gated tests ran **11 OK, 0 skipped** locally; this is the R9 merge gate, so carry `validation/maf-gated.log` in the PR body;
- five mutation checks (M1a masked, then covered; M1b; M2; M3; M4);
- quality and security reviews, all findings dispositioned.

## Deviations from the parent plan

- The seal is v8 only (E3), and `lead_generation <=` (E4) relaxes the merged validator.
- The live-run fence (E5) is new.
- The seal bumps the owner generation.
- The legacy receipt-digest fallback was dropped. A v8 predecessor sealed before `sealed_receipt_sha256` existed makes its successor fail closed.
- The AC9.1 test now models a stale generation by editing `run.json`.

## Residual risks

- **L1:** a v8 `unknown` send blocks lead changes until chunk 2 adds v8 resolution. Abandonment stays available.
- **L2:** receipt `lineage_usage` is self-reported within the cap bounds; the ledger is authoritative.
- **L3:** the non-blocking `recovery_lock` probe runs inside `run_lock`, inverting the documented order. It cannot deadlock.
- **Untested:** an `unknown` manager call as the guard trigger, and the lineage count on the recovery regrant path.
- **Chunk 2 must:** add the lineage count to `regrant_not_dispatched` and any v8 resolution regrant, and take `recovery_lock` in v8 `resolve-execution`.
- **Carried:** `send_lock` lacks `O_NOFOLLOW`; the read-only URI is built from the raw path; CI has no MAF job.
- **Found in passing:** `runstate._orchestration_gate_errors` fails on an unresolved root under macOS `/var` → `/private/var`. The tests pass a resolved root.

## Next actions

1. Run `/flow-review chartered-delivery-recovery-1b`.
2. Open the 1b PR with the MAF log once the engineer asks.
3. Open chunk 2 as its own linked run.
