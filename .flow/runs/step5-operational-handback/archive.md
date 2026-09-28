## Archive Summary

### Work Closed
- **Run:** `step5-operational-handback`, the last MAF adoption step 5 slice except MCP handback.
  - Branch `codex/step5-operational-handback`, commits `a51f4f1`..`87b99ba` plus this archive commit.
  - Review accepted on 2026-09-27 (`review.md`).
- **Trace correlation:**
  - Paid v8 manager observations keep the provider identity.
  - Each allowed manager call gets a canonical 0600 request file, written before its grant is consumed.
  - Every grant change emits a `grant_changed` event; a structural test covers every SQL write site.
  - Process-group lines name the call they served, and checkpoint links record their parent.
  - `recover-delivery-lead --actor` is now required.
  - `flow run trace` shows the per-call chain, led by a banner that says why an attempt is stuck.
- **Token budget:**
  - The v4 Shaper Contract and Delivery Charter seal a lineage token budget, with `tokens` headroom counted in tranches.
  - Usage is charged in `charged_v1`, by status, conservatively for usage shapes Flow doesn't recognise (RS1).
  - The check runs before every paid grant: a shortfall one tranche can clear expands under ADR 0017, otherwise the attempt pauses for a decision, including at zero headroom (R10 amendment); a shortfall of more than one tranche, or past the ceiling, is refused hard.
  - Receipts carry a recomputed `token_usage` block.
- **Seals:** both seals compare every row through one shared function, and the v8 receipt is built under the sealing `send_lock`.
- **`flow run verify-receipt`:** 17 offline checks, a requiredness table per terminal status, and failures that name what differs.
- **Pre-release v8 attempts** stay readable and abandonable, but can't be started or advanced.
- **Docs:** ADR 0020, the design doc (step 5 status and proof status), the CLI reference, the command catalogue and the regenerated help.

### Validation
- **Automated:**
  - The full suite: 1,771 OK, 0 skipped, with `FLOW_MAF_PYTHON`, green after every commit.
  - All 23 acceptance criteria pass, plus AC12b and AC12c (`validation-results.md`).
  - AC16's tamper suite asserts exact failing sets, with two justified deviations.
  - 14 mutation checks, all caught.
  - A stock-runner lineage verifies.
- **Manual:**
  - `trace` and `verify-receipt` against the real `v8-live-validation-3` run, whose tree was unchanged afterwards. Trace marks it `unsupported_contract`; verify refuses it as `unsupported_receipt` (exit 2).
  - `inspect-delivery` and `stuck` still read the pre-release run.
- **Runtime/deploy:** no live provider run on a v4 charter yet; that is `v8-live-validation-4`. The branch is not pushed or released.

### Residual Risks
- Granted-but-unsent calls reserve no tokens, which is the concurrent overshoot bound Andy chose (R12, RS2).
- A usage block with no readable counter at all still charges exactly the sealed amount; it is reported as unrecognised.
- Providers are stubs in tests. The Codex manager identity is proven at the contract level only.
- The sealed Delivery Charter of this run records the definition bytes from before the R10 and R9 amendments (`definition-dispositions.md`).

### Follow-up Work
- A PR, a merge and a release (each needs Andy's word). Then `v8-live-validation-4` on a v4 charter, exercising trace, the cap and verify-receipt live.
- QR17: compute the lineage charge once per action decision.
- Backlog, still open: the per-job charter digest; evidence symlink hygiene; MCP handback.

### Capability Gaps Observed
- **Hand-made amendments.** Approved-definition amendments after sealing (R10, then R9) were edited in place by hand, with no lifecycle step, and the sealed charter keeps the old bytes.
- **Manifest by copy.** The orchestration manifest was again built by copying another run's JSON. A later-lane review assignment couldn't be declared at definition time, because dispatch validation requires its inputs to exist.
- **Read-only reviewers.** Review roles couldn't run the suite, git or mutation checks, so every command was run by the coordinator.
- **Mutation harness.** Fourteen mutation checks were scripted by hand again, including checks that each edit applied and re-runs after patterns moved.
- **Report capture.** No command saves a delegated role's final report verbatim as a run artifact; review outputs were copied, or extracted from agent transcripts.
- **Ledger updates:**
  - `solution-amends-approved-definition`: reuse;
  - `orchestration-manifest-assignment-command`: reuse;
  - `reviewer-role-command-execution`: reuse;
  - `mutation-check-harness`: reuse;
  - `subagent-report-capture`: new.
- **Repeats:**
  - `reviewer-role-command-execution`: 9 (already promoted);
  - `orchestration-manifest-assignment-command`: 5 (already promoted);
  - `mutation-check-harness`: 5 (already promoted);
  - `solution-amends-approved-definition`: 3 (open; offered for promotion).

### Memory Updates
- **STATE** (`.flow/memory/STATE.md`): the run moves from active work to recently completed; the next steps are the PR, release and `v8-live-validation-4`.
- **Runtime memory entries written:** `project_flow_operational_handback.md`, a new entry covering ADR 0020's commands, the v4 token budget rules, the test fixtures and the next steps; indexed in `MEMORY.md`.
- **Parent-overlay implications:** none.
