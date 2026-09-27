# Reconciliation: step5-operational-handback

## Claims

- `research/current-state.md` is the only research note. It tags every claim as observed or inferred, with a file:line citation.
- The definition root spot-checked the research's central claims before drafting:
  - the enforceable-limit field set is exact (`cli/delivery_contracts.py:33-37`);
  - the expansion ceilings (`:40-46`);
  - the `v8-live-validation-3` `receipt_check.py`, read from branch `codex/v8-live-validation-3`. The research agent could not find this file; it is on that unmerged branch (PR #48).
- The research's inferred claims carried into the definition are marked as assumptions or open questions (requirements "Assumptions" and "Open questions"). None is stated as fact.

## Provider identities

- `definition-root`: this Claude Code session.
- `research-current-state`: one solution-architect subagent (Claude, opus).

## Status

Resolved. No conflicting claims.

## `receipt_check.py` mapping (F20)

- **Source:** `git show codex/v8-live-validation-3:.flow/runs/v8-live-validation-3/scripts/receipt_check.py`, 119 lines, read by the coordinator on 2026-09-27.
- **Calibration input:** the same branch's `execution/def92b2b…/receipt.json`, which gives the P10 values.

| receipt_check.py check | Covered by |
|---|---|
| `validate_receipt(envelope, receipt)` | V2 |
| `sealed_sha_matches` (file sha against the ledger) | V1 |
| envelope `expansion_headroom`, roster, predecessors | V7 (limits projection), V6 (predecessors); trace per-attempt header |
| per-action provider and `evidence_level` | V3 (full rows); trace rows |
| manager `(call_id, sequence, status)` | V3; trace rows |
| `local_stub` scan over the receipt, events and attempt files | **Not covered.** It is run-specific: the live run's claim was "no stub evidence". |
| expansion requests with authority | V4 (`expansion`); trace expansion rows |
| manager sequences contiguous | V3 (the rows equal the ledger), plus a new explicit item in V15: manager sequences are contiguous from the first. The plan adds it. |
| counts of `manager_send_started`, `manager_response_observed` and `adapter_send_started` per action | V15 (exactly one send start per sent row, per kind) |
| `manager_progress` | V4 |
| recovery modes | V5; trace per-attempt header |
| D1 event-log size, stream records and terminal result event | V14 (sha and bytes). The content-shape checks (stream records, terminal result) are **not covered**; they were specific to fix D1. |
| D1 limit errors in events | trace rows show event details; there is no dedicated check (fix-specific). |
| D7 chartered-facts line in checkpoints, including base64 | **Not covered** as a text search. V10 now gives the manager's request text directly, so the equivalent live check becomes `grep` over `manager-requests/`, with no decoding. |
| AC5/AC6 sends before the pause, between pause and decision, and after the decision | V15 (no send inside a pending-escalation window, by seq); trace banner and rows |
| AC4 auto grant `consumed_by` against the denied row | V4 (the expansion block replay) and V15 (each consumed grant has its consumption event) |
| D3 verifier evaluations non-empty | V3 and V11/V12 (final evaluation); the R14 table requires them on completed attempts |

**Remaining after this slice:**
- the stub scan;
- the D1 event-log content shape;
- the chartered-facts text search, which becomes a plain `grep` over request files.

All three are run-specific. The success criteria say so.
