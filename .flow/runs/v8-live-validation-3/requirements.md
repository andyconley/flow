# Requirements: v8 live validation 3 (third live chartered v8 job with expansion)

- **Status:** revised after adversarial review (`adversarial-review.md`, dispositions in `definition-dispositions.md`), pending engineer approval.
- **Date:** 2026-09-27.
- **Basis:** adapted from `v8-live-validation-2`, which carried over `v8-live-validation`'s definition. It changes only what the D3–D7 fixes and step 5 cancellation require. Everything not listed under "Changes" carries over from `v8-live-validation-2/requirements.md` unchanged: the job, its proof, write scope, roles, R2, R5, R7, R8, the budget, isolation and the known risks.

## Problem

Every v8 chartered path is proven with stubs, and both live runs ended in Flow defects:
- `v8-live-validation` ended on D1 and D2;
- `v8-live-validation-2` ended on D3–D7.

All seven defects are now fixed and released:
- D1 and D2 in v0.36.1;
- D3 in v0.36.2;
- D4 and D5 in v0.37.0;
- D6 and D7 in v0.37.1.

`v8-live-validation-2` proved the escalation, `decide-expansion`, the pending-mode resume, lineage accounting and a sealed receipt live. It did not prove:
- an automatic grant;
- a manager-call replay across a resume;
- a live local-verifier evaluation;
- a completed job.

v0.38.0 (`step5-cancellation`, ADR 0019) also removes the dead end that limited the earlier runs. A stuck attempt can now be abandoned, and a successor can run on the same work id.

## Changes from `v8-live-validation-2`

1. **Release.** `flow` v0.38.0 or later is installed before `start-plan`. It contains the D3–D7 fixes and the cancel and abandon CLI. The specialist digests from the installed CLI still equal the sealed values: `tech-writer` `9daf3e0f…` and `quality-reviewer` `1ee52e24…`, checked on 2026-09-27 against v0.38.0.
2. **The job and worktree are unchanged.**
   - The worktree `~/src/flow-v8-live-job-2` is reused on `job/decide-expansion-docs-2`, at the job commit `d6d771f2`, where the targeted test fails.
   - It was clean at that commit on 2026-09-27.
   - The job charter is byte-identical to `v8-live-validation-2`'s (sha256 `fef21732…`).
   - Its worktree `.flow` is the tracked copy from that commit, not the project `.flow`, so prepare allows it (the dev/inode check, as before).
3. **Manager guidance (D7).** The chartered manager facts now state that the approved editors get one call in total, which must make the complete edit. No other manager prompting is added, and nothing is staged.
4. **Stuck attempts no longer end the run (replaces Change 5 of `v8-live-validation-2`).**
   - **An uncertain send** ends that attempt: a provider call raised before Flow observed its completion, or an adapter timeout (manager over 120 s, producer over 300 s, verifier over 60 s). The call is marked `unknown`, and the attempt can't be resumed. The operator then runs `flow run stuck` and `flow run abandon-delivery … --expected-generation N`, which seals it `abandoned` with the send kept `unknown`.
   - **A successor attempt** on the same work id then prepares normally. It lists the abandoned attempt as a predecessor and counts its uncertain paid send as spent. It needs a clean worktree, so the worktree is first reset to `d6d771f2`. The reset is recorded.
   - **The 600 s launch deadline** stays recoverable, as before. The next protocol step records a transport interruption, and `recover-delivery-lead` continues the same attempt.
   - **Cancel is not staged.** `cancel-delivery` is used only if a live attempt must be stopped for an operational reason, for example a runaway call or the wrong model. Any use is recorded with its reason.
5. **Paid-call headroom (engineer decision, 2026-09-27: option a).**
   - Paid worker calls and verifier calls count across the whole lineage, and so does all headroom: every automatic grant uses up a lineage unit, and units are never refilled.
   - So after an attempt that sent its one paid edit, a successor's edit doesn't hard-fail. It becomes an expansion request.
   - The intent seals `paid_worker_calls` headroom 1, so that request is **granted automatically**. The alternative, headroom 0, would escalate it for a decision.
   - Accepted tradeoff: no one reads the successor's editor task before that paid send. If the manager still delegates an inspect-only turn, D7 being guidance only, the lineage's last automatic paid unit is spent and the attempt fails as "editor made no edit".
   - Edge case: if attempt 1's editor action ends `not_dispatched` and is proposed again, the unit is spent inside attempt 1, and a successor's edit then escalates. That is recorded, and it is not a defect.
6. **D4 and D5 are expected to hold live.**
   - **D4:** a malformed manager progress reply is repaired or retried, as counted manager calls that aren't rounds. That can move the grant and escalation to earlier call numbers.
   - **D5:** recovery succeeds after a headroom grant, which is exactly the call-5 grant followed by the call-6 escalation.
7. **Evidence tooling.** `scripts/ledger_timings.py` and `scripts/verifier_gate.py` are copied from `v8-live-validation-2`. They read per-call timings from the ledger and run the realistic verifier warm-up gate. `inspect-delivery` still doesn't project timings (gap `delivery-per-call-timings`).

## Audience

Andy, Flow's only operator, as before.

## Desired outcome

**Primary: validate the full v8 chain end to end with real providers.** This is the same as `v8-live-validation-2`, with this run's focus on what is still unproven: the automatic grant (AC4), a manager-call replay (AC6), a live verifier evaluation, and a completed job (AC8 `completed`). The documentation change stays secondary and best-effort.

## Requirements

- **R1, sealed authority.** Same as `v8-live-validation-2` R1, except that the headroom is manager calls 1, delegations 1, verifier calls 1 and paid worker calls 1 (Change 5). The base limits are unchanged: delegations 2, paid worker calls 1, verifier calls 1, manager calls 4, manager rounds 6.
- **R2 (manifest), R3 (live execution), R5 (evidence), R7 (defects) and R8 (the documentation change)** are unchanged.
- **R4, expansion events.**
  - **In the first attempt:** manager call 5 is expected to be granted automatically, and call 6 to escalate for Andy's decision and resume in answer mode. Rounds can't escalate: base 6 is the runner ceiling, and a seventh round is a hard denial.
  - **D4 shift:** a retried or repaired progress reply is a counted call, so it can move both events earlier. The run records the actual call numbers, and whether the paused call was a D4 retry.
  - **Lost events:** a manager that skips review gets only the automatic grant. An inspect-only editor turn fails before either event.
  - **In a successor:** the manager headroom is already spent across the lineage, so its call 5 escalates. AC4 in a successor is met by any automatic grant. The likely ones are the paid edit (Change 5), or a verifier retry if that unit is unspent.
- **R6, attempts.**
  - Up to two live attempts, and AC1–AC9 apply to each.
  - A second attempt is a successor after any terminal predecessor (`failed`, `abandoned` or `cancelled`). It runs under the same sealed limits, on the worktree reset to `d6d771f2`. Limits can't be retuned after `start-plan`, which seals the charter. Supersede has no CLI, so it is only a Python fallback, recorded as a gap under R9.
  - **Verifier precondition:** the verifier ceiling of 2 applies to the whole lineage. A successor is launched only if the lineage still has a verifier send available: at most 1 predecessor verifier send, and the verifier unit unspent if the base is already used. This is checked from `inspect-delivery` before launch. A successor has no verifier retry.
  - Verifier behaviour is never staged.
- **R9, operator surface (new).** Any stop, stuck state or abandon in this run uses the v0.38.0 CLI (`stuck`, `inspect-delivery`, `abandon-delivery`, and if needed `cancel-delivery`). A step that needs Python instead is recorded as a gap.

## Non-goals

- Changing Flow's code in this run (R7).
- Codex as a provider, replan expansion, the specialist pool, trace correlation, MCP handback and token caps.
- Staging a cancel, an abandon, or any provider behaviour.
- Measuring quality or latency beyond observed usage and timings.

## Constraints

- **Budget.** The charter caps enforce it.
  - **Per attempt:** 4 manager calls, plus approved escalations (plus 1 automatic, in the first attempt only); up to 2 verifier calls; 600 s per launch.
  - **Across the lineage of up to two attempts:**
    - at most 2 paid Claude edits (1 base plus 1 automatic);
    - at most 2 verifier sends (the runner ceiling);
    - at most 1 automatic manager call.

    Every other manager call past the base is approved by Andy one at a time.
  - **Target wall time:** about 30 minutes per attempt, and about 60 minutes for two.
- **Local setup.** Ollama is running with `gemma4:26b`, the Claude CLI is authenticated, `FLOW_MAF_PYTHON` points at `~/.flow/venvs/maf`, and v0.38.0 or later is installed.
- **Preflight, before each launch.** The same gate as `v8-live-validation-2`:
  - `ollama list`;
  - a warm-up, then one timed realistic diff-sized review call, as a go/no-go gate well inside 60 s;
  - Claude authentication;
  - the installed version;
  - the specialist digests;
  - `validate-orchestration --stage dispatch`;
  - the worktree clean at `d6d771f2`.

  In addition:
  - `flow run stuck` must list no started attempt for this work id before any launch.
  - **Before a successor:**
    1. save the worktree `git diff` to evidence;
    2. run `git reset --hard d6d771f2 && git clean -fd`;
    3. confirm `git status --porcelain --untracked-files=all` is empty (prepare checks untracked files too);
    4. check the R6 verifier precondition.

## Known risks

- `manifest-timeout-enforcement` still applies: the adapter caps are fixed in code.
- `handback-unreached-assignment-outputs`: unreached assignments get honest "not reached" outputs.
- **Adapter timeouts.** A manager turn over 120 s, a producer turn over 300 s or a verifier turn over 60 s is an uncertain send, and an accepted environmental or model-latency outcome. With v0.38.0 it costs an attempt, not the work id. It counts as a Flow defect only if the provider's completion was observed inside the cap, or if a D1-class stream, output or trace cap cut the turn off.
- **D7 is guidance only.** A manager that still delegates an inspect-only turn now fails fast, as "editor made no edit". That is a legitimate AC8 outcome, recorded as model behaviour, not as a Flow defect.

## Assumptions

- **A1.** v0.38.0 exposes `execute-chartered-job`, `decide-expansion`, `inspect-delivery`, `recover-delivery-lead`, `stuck`, `abandon-delivery` and `cancel-delivery`. This was checked with `flow run --help` on 2026-09-27.
- **A2.** Unchanged: the job charter reaches prepare through the manager assignment's `input_evidence`, and its sha256 is recorded at `approve-plan` (gap `job-charter-sealed-digest`).
- **A3.** Unchanged: about 6 manager calls when the first review passes.

## Open questions

None. Both questions are closed:
- the paid headroom is 1 (Change 5, engineer decision);
- the manager base stays at 4 with headroom 1, and the actual call numbers are recorded (R4).
