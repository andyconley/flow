# Archive Summary

## Work Closed

- **Run:** `v8-live-validation`, the first live v8 chartered job on real providers (flow v0.36.0). The review was accepted as "validation found defects" (R7).
- **What changed:** no Flow code. The run produced run artifacts and evidence only.
  - The job branch `job/decide-expansion-docs` (worktree `~/src/flow-v8-live-job`) holds only the job test, at commit `c864241`.
- **Outcome:** attempt `f628faa9…` was interrupted after 137 s, and its AC8 outcome is **Flow defect** (D1).
  - The Claude edit worker aborted once its stream passed the 1 MiB `MAX_EVENT_BYTES` cap.
  - Flow correctly marked the edit `unknown` and resent nothing.
  - The lead claim was released, so this work id can't execute again.
- **Proved live:**
  - sealed v3 authority, including expansion headroom;
  - real preparation against a pinned worktree;
  - 3 Flow-gated Claude manager calls;
  - a Flow-granted Claude edit with its write scope enforced;
  - fail-closed handling of an uncertain send.
- **Not reached:** the automatic grant, escalation and its decision, identical replay, and a sealed receipt (AC4–AC7).
- **Latent defect D2:** `scripts/regenerate-flow-help.py` emits raw `|` inside Markdown table cells.

## Validation

- **Automated:** the baseline job test failed as designed (A8). A scratch contract proof passed 3 of 3 tests. No Flow tests were affected, because no code changed.
- **Manual:**
  - preflight (model warm, Claude signed in, digests matched, MAF import);
  - the charter sha256 matched the value frozen at approve-plan;
  - D1 was diagnosed against the code and the events log, which stopped at exactly 1,048,576 bytes;
  - D2 was reproduced with a targeted test run.
- **Runtime:** one live launch on real Claude, with the evidence in `evidence/`. Per-call timings weren't captured.
- **Mutation check:** not applicable, because no code changed.

## Residual Risks

- The live expansion chain (grant, pause, decide, replay, receipt) is still unproven.
- Until D1 is fixed, any realistic Claude edit that reads large files will be interrupted.
- The job charter's integrity rests on a hand-recorded sha256.

## Follow-up Work

1. **Fix run.**
   - D1 (`fix(cli)`):
     - split the edit worker's read limit from its log cap;
     - parse the stream line by line under a memory ceiling;
     - fix the debug-trace abort;
     - review `--include-partial-messages`;
     - test that a stream over 1 MiB completes.
   - D2 (`fix(scripts)`): escape pipes in the help generator and regenerate the tables.
2. **`v8-live-validation-2`,** after the fix is released. It reuses this definition and runbook, but needs a new job test and baseline for escaped pipes, a new charter sha256, and per-call timings.
3. **Cleanup:** remove the worktree `~/src/flow-v8-live-job` once the next run creates its own.

## Capability Gaps Observed

- **Lead release or supersede:** there is no CLI for either. Release went through a direct `delivery_control.change_lead_claim` call. (`delivery-lead-claim-cli`, new)
- **Job charter:** it isn't covered by the sealed digests; only a recorded hash protects it. (`job-charter-sealed-digest`, new)
- **Timeouts:** manifest per-assignment timeouts are ignored on the Ollama verifier path. (`manifest-timeout-enforcement`, new)
- **MAF interpreter:** the durable venv was built and import-checked by hand. (`maf-runtime-interpreter-preflight`, a reuse, now seen 4 times)
- **Handback gate:** it demands outputs for manifest assignments the run never reached. (`handback-unreached-assignment-outputs`, new)
- **Repeats:**
  - `maf-runtime-interpreter-preflight` (4);
  - still open from earlier: `reviewer-role-command-execution` (5) and `orchestration-manifest-assignment-command` (3).

## Memory Updates

- **STATE:** the validation run is closed with defects found. The D1/D2 fix run and `v8-live-validation-2` are the next work.
- **Runtime memory:** `project_flow_delegated_expansion.md` has a new live-validation section.
