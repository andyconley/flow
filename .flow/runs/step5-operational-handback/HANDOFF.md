# Handoff: step5-operational-handback

## What shipped

On branch `codex/step5-operational-handback`: seven planned commits, plus one review-refinement commit. MAF adoption step 5 is complete, apart from MCP handback (ADR 0020).

- **C1 `a51f4f1`: correlation.**
  - Paid v8 manager observations keep the provider identity.
  - Canonical 0600 manager request files are written before the grant is consumed.
  - `grant_changed` records every grant change, with a structural test over all SQL write sites.
  - Process-group lines name the call they served, and v8 checkpoint links record their parent.
  - `recover-delivery-lead --actor` is required.
- **C2 `d629b59`: `flow run trace`.** Per-call rows, grant history, sessions, request files, pgids, checkpoints, timings and usage, led by a banner that says why an attempt is stuck.
- **C3 `f246839`: the v4 token contract.**
  - The contract seals `max_lineage_tokens`, `token_tranche` and `unobserved_send_tokens`, plus `tokens` headroom counted in tranches.
  - Charging is pure and by status, in `charged_v1` units.
  - Usage checks tolerate unknown keys.
  - Pre-release v8 attempts stay readable and abandonable, but can't be started or advanced.
- **C4 `e8d8af4`: the pre-grant token check on every paid path.** ADR 0017 expansion is automatic within headroom, and otherwise pauses (including at zero headroom, as amended). A shortfall of more than one tranche, or a tranche past the ceiling, is refused hard. The recovered manager reissue is fully checked.
- **C5 `7ca8506`: sealed tokens and full-row seals.** The receipt carries `token_usage`, and one shared full-row comparison is used by both seals. The v8 receipt is built under the sealing `send_lock`.
- **C6 `9e1d123`: `flow run verify-receipt`.** Seventeen offline checks, the R14 requiredness table, and diagnostic failures.
- **C7 `d1bcc5f`: docs.** ADR 0020, the design doc, the CLI reference, the command catalogue and help.
- **Review refinement `6106762`.**
  - QR1–QR11, QR13–QR16 and QR18: verify accuracy on non-completed and damaged receipts; V15 reads the ledger; seal and gateway tidy-ups.
  - TR1–TR3.
  - Security RS3–RS7: bounded reads, id validation, catch-all per check, and a note that request files are sensitive.

## Proof

- **Full suite:** 1769 tests OK, with 0 skipped, using `FLOW_MAF_PYTHON`. Help is up to date.
- **Acceptance criteria:** all 23 pass, plus AC12b and AC12c (`validation-results.md`). The AC16 tamper suite asserts exact failing sets, with two documented deviations.
- **Mutations:** all 13 are caught.
- **Real data:** trace and verify were run against `v8-live-validation-3`. Trace reads it and marks it `unsupported_contract`; verify refuses it with `unsupported_receipt` (exit 2). The run tree is unchanged.
- **Stock runner:** one lineage through the pinned stock Magentic runner verifies cleanly.

## Decision needed from Andy

**RS1 (security, Important).** A paid call whose usage has a shape Flow doesn't recognise is charged the sealed `unobserved_send_tokens`, as approved in R9, P2 and F3. If a provider CLI changes its usage shape, every call would be charged that fixed amount, and the cap would under-count.

The options:
1. **Keep as approved.** The count is reported in `token_usage.unrecognised_usage` and trace.
2. **Conservative charge.** Charge the maximum of U, `total_tokens`, or the sum of the known counters present. It stays deterministic, amends R9 slightly, and is recommended.
3. **Hard gate.** Make unrecognised usage a hard gate condition, which amends R9 and F3.

## Residual risks and follow-ups

- **RS2 / R12:** grants that are allowed but not yet consumed reserve no tokens. This is the concurrent overshoot bound you chose, and it is documented.
- **No live v4 run yet.** Real providers under a v4 charter have not run; `v8-live-validation-4` should exercise trace, the cap and verify-receipt live.
- **QR17 (performance):** the lineage charge is computed twice per action decision.
- **Codex manager identity:** proven at the contract level only.
- **Out of scope, still open:** the per-job charter digest and evidence symlink hygiene (non-goals; both are in the backlog).
- **Sealed records:** the sealed Delivery Charter of this run records the R10/AC10 bytes from before the amendment (`definition-dispositions.md`).

## Next

1. `/flow-review step5-operational-handback`.
2. Andy decides RS1.
3. Commit and push the run records and open a PR, which needs Andy's word.
4. Release, then `v8-live-validation-4` on a v4 charter.
