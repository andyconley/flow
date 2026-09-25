# Validation Plan: shaper-expansion-approval

All proof is hermetic, using stub providers and the pinned MAF interpreter. There is no live provider run in this slice.

## Environment

- `python3.12 -m unittest discover -s tests`, with `FLOW_MAF_PYTHON=<scratchpad>/maf-venv/bin/python` (agent-framework-core 1.19.0, agent-framework-orchestrations 1.2.0).
- The fail-closed runner (`scratchpad/suite-main.sh`) fails on any failure *or* skip. It runs before every commit and before handback.

## Acceptance criteria mapping

| AC | Proof | Test location |
|---|---|---|
| AC1, headroom sealed | Sealing with and without headroom; refusal of negatives, unknown or non-expandable keys (replans, concurrency), verifier total above 2, and base + headroom above each ceiling; derived `delegated_expansion` | `tests/test_shaper_delivery_contracts.py` |
| AC2, request and pause | For each of the five reasons: one request keyed on the denied row, amount 1, headroom remaining; `expansion_paused` status (not interrupted, not failed); no worker send and no manager response for the paused proposal; claim active at the same generation; status, list and inspect display | `tests/test_expansion_ledger.py`, `tests/test_chartered_delivery_gateway.py` |
| AC3, hard denials | Each hard reason produces no request row and its existing denial, *including* when an expandable cap also fails (A3: verifier retry plus verifier cap; replan not authorized plus manager-call cap) | `tests/test_expansion_ledger.py` |
| AC4, automatic approval | Grant within headroom under `charter_headroom` authority; exhaustion then escalation; idempotent replay; crash test (T2): a failure injected before commit rolls back both (a rerun records one request and one grant); a replay after commit returns the same request with no second draw; the oracle is the grant count and headroom remaining | `tests/test_expansion_ledger.py` |
| AC5, decision | Approve and deny; a manual grant doesn't draw headroom; refusals for stale generation, unknown request, already decided, not paused (started or unknown row; lock held) and ceiling exceeded, each asserting no row changed | `tests/test_expansion_decide.py` |
| AC6, resume after approval | The paused proposal is replayed with the same identity; row changes `denied` → `allowed` (`expansion_granted`) and the denial is kept in events and the request row; no completed action re-sent; effective limit = base + grants; a second replay gets `expansion_grant_consumed` | `tests/test_expansion_recovery.py`, `tests/test_maf_expansion.py` |
| AC7, resume after denial | Worker: denial reported to the manager, and the attempt completes within the charter. Manager (E5 a): the attempt is sealed `failed` with reason = the limit, and no Flow-authored manager text is sent; a re-decision is refused; a re-proposal creates a new request that escalates | `tests/test_expansion_recovery.py`, `tests/test_maf_expansion.py` |
| AC8, lineage (E6 a) | A grant raises only its limit's counter; a successor inherits remaining headroom and lineage-counter grants (paid, verifier) but not per-attempt grants; unused grants on a superseded attempt become `lapsed`; no refill; supersede and release cancel pending requests | `tests/test_expansion_ledger.py`, `tests/test_expansion_recovery.py` |
| AC9, receipts | All requests and decisions listed. One test per tamper case (T4): `test_receipt_rejects_added_grant`, `…_removed_grant`, `…_altered_grant`, `…_auto_beyond_headroom`, `…_wrong_authority`, `…_amount_above_one`, `…_foreign_lineage`, `…_foreign_generation`, `…_expansion_granted_without_grant` | `tests/test_expansion_receipts.py` |
| AC10, atomicity | Deterministic via `threading.Barrier(2)` + `ThreadPoolExecutor` (pattern: `tests/test_structured_verifier_ledger.py:131-137`); no sleeps (T1). Two concurrent decisions: one winner, one `expansion_already_decided`. Decide racing a supersede: one outcome. Lock-order assertion. Manager-supplied amount and rationale fields ignored | `tests/test_expansion_decide.py` |
| AC11, other protocols | The existing v5–v7 tests pass unchanged; explicit tests that v5, v6 and v7 attempts hitting `delegation_cap` and `paid_call_cap` keep the legacy denial shape with no request row (T5) | The whole suite, plus `tests/test_expansion_ledger.py` |
| AC12, proof | 0 failures and 0 skipped with `FLOW_MAF_PYTHON`; the 7 mutation checks below | `validation-results.md` |

## MAF-gated end-to-end tests (`tests/test_maf_expansion.py`)

These use the real runner and stub providers.

All cases use `shaper_intent(limits=…, expansion_headroom=…)` from the fixture (T6).

1. **Automatic approval:** `max_delegations` base 1, headroom 1. The second delegation is granted inline, with no pause.
2. **Worker escalation:** base 1, headroom 0. Pause, then `decide-expansion --approve`, then `recover-delivery-lead`. The proposal replays with the same `action_id`, and the attempt completes.
3. **Manager escalation, approve:** `shaper_intent(limits={"max_manager_calls": 8}, expansion_headroom={})`. Pause, then `--approve`, then recover. The denied `call_id` is replayed under the grant, and the attempt completes.
3b. **Manager escalation, deny (E5 a):** the same setup, then `--deny`. The attempt is sealed `failed` with reason `manager_call_cap`, and no manager text is written by Flow.
4. **Manager escalation before any worker checkpoint:** recovery chooses `restart` mode. Planning calls replay from the ledger, and the denied `call_id` is allowed under the grant.
5. **Replay-identity regression:** spike scenarios S2, S2b and S3 as pinned tests asserting identical `call_id`s. This is the MAF-pin tripwire (T6).
6. **Supervisor ceiling (A1):** a grant that takes manager calls above base + 1 runs without `MafProtocolError`.

## Mutation checks (AC12)

For each check: apply the mutation, run the named test, confirm it fails, restore, and confirm it passes. The results go in `validation-results.md`.

| # | Mutation | Expected failing test |
|---|---|---|
| M1 | Remove the headroom bound (always auto-grant) | AC4 exhaustion-escalates test, which asserts `expansion.status == pending` with the effective limit below the ceiling (T3) |
| M2 | Send before pausing (skip the `ExpansionPaused` raise on the worker path) | AC2 no-send test |
| M3 | Remove the generation fence in `decide_expansion` | AC5 stale-generation test |
| M4 | Remove the truly-paused guard | AC5 not-paused refusal test |
| M5 | Remove the `consumed_by` check | AC6 single-consumption test |
| M6 | Skip receipt headroom recomputation | AC9 automatic-spending-beyond-headroom test |
| M7 | Route an expansion pause to `record_interruption` (drop the recovery mode) | AC2 pause-status test and AC6 resume test |

## Reviews

- **Plan:** architect (architecture) and test-engineer (validation), read-only, before `approve-plan`.
- **Implementation:** quality-reviewer and security-reviewer, independent, before `mark-handback-ready`. Findings and dispositions go in `implementation-review.md`.

## Exit criteria

- AC1–AC12 each have a passing test that was named in advance.
- The suite passes with 0 failures and 0 skipped.
- M1–M7 are all recorded as caught.
- Review findings are dispositioned.
