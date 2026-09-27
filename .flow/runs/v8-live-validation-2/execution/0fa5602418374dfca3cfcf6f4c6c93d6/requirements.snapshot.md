# Requirements: v8 live validation 2 (second live chartered v8 job with expansion)

- **Status:** revised after adversarial review (`adversarial-review.md`), pending engineer approval. Adapted from `v8-live-validation` (engineer decision, 2026-09-26: reuse that definition and change only what the D1/D2 fixes and its findings require).
- **Date:** 2026-09-26.

## Problem

Every v8 chartered path was proven only with stub providers. The first live run, `v8-live-validation` (archived 2026-09-26, PR #39), got through sealed authority, preparation, 3 Flow-gated Claude manager calls and a Flow-granted Claude edit. It was then interrupted by a Flow defect, D1: the Claude edit worker aborted once its stream passed 1 MiB, so the edit was marked `unknown`. It never reached the expansion chain or a sealed receipt. The run also surfaced D2: the help generator wrote raw `|` into table cells.

Both are fixed by `edit-worker-stream-cap`, merged as PR #38 and released as v0.36.1:
- the edit worker's stream cap is now 16 MiB;
- partial messages are no longer requested;
- an oversized debug trace is truncated instead of aborting the turn;
- generated table cells escape `|` as `\|`.

That run's work id can never execute again, because its lead was released and its attempt stays `started`. This run repeats the validation under a new work id.

## Changes from `v8-live-validation` (engineer decisions, 2026-09-26)

1. **Job contract.** Generated table rows escape `|` as `\|`, so the `decide-expansion` row reads `(--approve \| --deny)`.
   - The job test's docstring and baseline are redone to match. That means a new job commit, and a new charter sha256 recorded at `approve-plan` (A7).
   - The job charter's task states the escaping explicitly, and says `flow.toml` keeps the raw `|` (architecture review I4).
   - The job test's docstring rule 2 is inverted: it now requires the escaped row, where before it said "do not write `\|`" (I5). The test code doesn't change.
2. **Release.** `flow` v0.36.1 or later is installed before `start-plan`, and the specialist digests are checked again against the sealed values.
3. **Worktree.** A fresh worktree, `~/src/flow-v8-live-job-2`, on branch `job/decide-expansion-docs-2` from current `main`. The first run's worktree and branch are removed once this run's attempt is prepared.
4. **Per-call timings (architecture review I3).**
   - The ledger `events` table already records microsecond UTC timestamps for every call:
     - manager: `manager_send_started` then `manager_response_observed`;
     - producer: `adapter_send_started` then `response_observed`;
     - verifier: `verifier_send_claimed` then `verifier_evaluated`;
     - expansion requests: `created_at` and `decided_at`.
   - `inspect-delivery` doesn't project them, so the evidence step reads them with `ExecutionLedger(path, read_only=True).snapshot(attempt_id)` through the installed CLI's Python.
   - The first run's timings, which are in its `ledger.sqlite`, are backfilled into this run's evidence. That corrects the first run's "timings weren't captured".
5. **Interruption handling (requirements review 1, architecture review C1 and I2).**
   - **An uncertain send ends the run's attempts.** This happens when any provider call raises before Flow observes its completion. That includes a provider timeout: manager over 120 s, producer over 300 s, verifier over 60 s.
     - The call is marked `unknown`, and the attempt can't be resumed (ADR 0016).
     - Release is the only route out, and a released attempt permanently blocks this work id.
     - Any further attempt then needs a new work id, which is out of scope for this run.
   - **The 600 s launch deadline is recoverable.** It is checked only on runner protocol reads and writes. A call in progress finishes and is recorded. The next protocol step then records a transport interruption with resume available, and `recover-delivery-lead` continues the same attempt.
   - The plan records both routes in advance.
6. **Evidence hygiene.** The Claude CLI's `--debug-file` writes an absolute `latest` symlink next to the trace. The first run committed it, and the dangling link broke the v0.36.1 release suite (fixed in PR #40). Evidence commits exclude symlinks, which is checked with `git ls-files -s` (no mode `120000`).

## Audience

Andy, Flow's only operator. He needs evidence that the whole v8 chain works with real providers before relying on it for real work.

## Desired outcome

**Primary: validate the v8 chain end to end with real providers** (P2). A run that exercises expansion and seals a valid receipt, but doesn't deliver the documentation, still meets the primary outcome. The documentation change is a secondary, best-effort outcome.

One real job runs through the real stack:

- Flow-sealed authority;
- a stock Magentic manager on Claude;
- a Claude producer editing an isolated worktree;
- Flow's diff and test verification;
- a local Ollama verifier.

The run exercises delegated expansion live: one automatic grant, and one escalated request that Andy decides and that is then resumed. It ends with a sealed, valid receipt whose evidence Andy can inspect.

## The job (engineer decisions 1a–3a, 2026-09-26)

- **Task.** Document the new `flow run decide-expansion` command:
  - its help entry in the `[[help.cli_commands]]` table of `scaffolds/default/flow.toml`;
  - the generated command tables in `scaffolds/default/commands/flow-help.md` and `README.md`, kept in sync;
  - a `docs/cli-reference.md` section covering syntax, refusals, and the decide-then-`recover-delivery-lead` flow.
- **Proof.** A new targeted test is committed on a job branch before the run, and fails there. The worktree's HEAD is that commit, sealed as a clean baseline. The test asserts:
  - the command is documented with its real flags;
  - the generated tables are in sync.

  The producer's edit must make it pass.
- **Write scope.** Exactly those four documentation files.
- **Roles.** Producer: `tech-writer` (Claude `sonnet`, scoped edit). Verifier: `quality-reviewer` (Ollama `gemma4:26b`, read-only). Manager: Claude `sonnet`.
- **Review is part of the job (A1).** The job's task says the change must then be independently reviewed, read-only, by `local-verifier` before it is done. This is a real acceptance requirement of the job, the same as for any chartered job. It is not staging: the manager still chooses its own path.

## Requirements

- **R1, sealed authority.**
  - The run seals a Shaper Contract and Delivery Charter at `start-plan`.
  - Allowed specialists: `tech-writer` (scoped edit) and `quality-reviewer` (read-only review), each pinned to its current definition digest, with at most 1 instance each.
  - Limits:
    - delegations 2, paid worker calls 1, concurrency 1;
    - verifier calls 1;
    - manager calls 4, manager rounds 6;
    - replans 0, retries 0;
    - runtime 600 seconds. This is the envelope maximum, and it can't be expanded. Each launch (the initial run, and each resume) gets its own 600-second deadline (A4).
  - Expansion headroom: manager calls 1, delegations 1 and verifier calls 1.
- **R2, manifest.** The manifest's `execution.timeout_seconds` and `max_output_chars` aren't enforced (gap `manifest-timeout-enforcement`). The effective caps are fixed in code: manager 120 s, producer 300 s, verifier 60 s. The manifest's 120 s for the verifier is therefore really 60 s. The orchestration manifest, frozen at `approve-definition`, carries the three implement-lane execution assignments: `magentic-manager`, `docs-editor` and `local-verifier`, with the providers, models and scopes above. It also carries the definition-lane review assignments.
- **R3, live execution.**
  - The job runs through `flow run execute-chartered-job` against an isolated worktree pinned to the job commit.
  - It uses real providers. There are no stubs in the execution path.
- **R4, expansion events** (why the limits above are set as they are). Even a run that passes on the first review makes about 6 manager calls: facts, plan, progress to select the editor, progress to select the verifier, progress to declare it satisfied, and the final answer. So:
  - **Automatic grant.** Manager call 5 goes past the base of 4 and is granted automatically from the one unit of manager headroom.
  - **Escalation.** Manager call 6 exceeds the remaining headroom and escalates for Andy's decision. This happens after both actions, so it resumes in answer mode from the verifier's checkpoint.
  - **Resume.** After each decision, `recover-delivery-lead` resumes the attempt.
  - **Verifier retry.** If gemma4 fails the first review, the retry is granted automatically too (one delegation unit and one verifier unit), and later manager calls escalate one at a time.

  Both events are therefore expected whenever the manager follows the task (edit, then independent review), without staging any provider. A shorter path (edit, then declare it satisfied with no review) would give only the automatic grant at call 5 and no escalation. R6 applies then.

  **A failed review can't be repaired in-attempt (A3).** A second producer call is a hard denial (`producer_already_completed`). A failing first review therefore leads to a verifier retry, which is granted automatically, and then the attempt seals `failed` unless the retry passes.
- **R5, evidence.** For each attempt, the run artifacts preserve:
  - `inspect-delivery` output before and after each decision;
  - the decision commands used;
  - the sealed receipt;
  - `validate_receipt` passing on it;
  - the ledger's expansion state;
  - replay-identity observations: the paused `call_id` is identical after resume, and no completed work is re-sent;
  - observed provider usage.
- **R6, attempts (engineer decision 4a).**
  - Acceptance criteria AC1–AC9 apply to each attempt (B5).
  - Reinstalling Flow between attempts, for example to fix a defect, can change the specialist definition digests and invalidate the sealed charter for a second attempt (A5).
  - Up to two live attempts are in scope.
  - If an expansion event doesn't happen, the run records what did happen. A second attempt (a supersede successor, so lineage headroom stays honest) with retuned limits is allowed.
  - Verifier behavior is never staged.
- **R7, defects.**
  - A Flow defect found live is recorded with its evidence, and fixed in its own run, not inside this one.
  - This run may end with a documented defect, which is a valid outcome for validation.
- **R8, the documentation change.** If the job completes, its diff and passing test are reviewed on their merits. The change may merge as real documentation.

## Non-goals

- Changing Flow's code in this run (see R7).
- Codex as a provider, replan expansion, the specialist pool, cancellation, trace correlation, MCP handback, and token caps.
- Staging or prompting the verifier or manager to force a path.
- Measuring quality or latency beyond observed usage and timings.

## Constraints

- **Budget.** It is enforced by the charter caps.
  - Per attempt, worst case: 4 manager calls, plus 1 automatic and up to 3 approved manager calls. The approved calls come from R4's verifier-retry path: each call past the single sealed headroom unit escalates on its own for Andy's decision, so none is granted silently; 1 paid Claude edit; up to 2 local verifier calls; 600 seconds of runtime per launch.
  - Replayed calls are free.
  - Target: about 30 minutes of wall time per attempt, including its resumes and Andy's decisions. The worst case for two attempts is bounded at about 60 minutes (P3).
- **Local setup.**
  - Ollama is running locally with `gemma4:26b`.
  - The Claude CLI is authenticated.
  - `FLOW_MAF_PYTHON` points to the pinned MAF interpreter.
  - `flow` is installed from the release containing the D1/D2 fixes (v0.36.1 or later).
- **Isolation.** The worktree is outside the project `.flow` tree. The v8 prepare step refuses a worktree that contains a project `.flow` directory.
- **Preflight (P1, A4, A5), done before each launch:**
  - `ollama list` shows `gemma4:26b`;
  - the model is warmed, then given one timed call with a realistic diff-sized review prompt. It is a go/no-go gate: the call must finish well inside Flow's 60 s verifier cap (architecture review C1);
  - the first run's worktree `~/src/flow-v8-live-job` isn't reused. The fresh path `~/src/flow-v8-live-job-2` exists, is clean and sits at the job commit, and this is recorded;
  - `claude` is authenticated;
  - the installed `flow` is v0.36.1 or later;
  - the specialist digests computed by the installed `flow` equal the sealed ones (`tech-writer` `9daf3e0f…`, `quality-reviewer` `1ee52e24…`; unchanged by the fix release, to be re-verified).

## Known risks carried from `v8-live-validation` (product review)

- **`manifest-timeout-enforcement`.** The fixed adapter caps (R2) are the real timeouts. Preflight mitigates the verifier's 60 s cap with a timed warm call (see Constraints).
- **`handback-unreached-assignment-outputs`.** If an attempt stops early, the handback gate still demands output files for assignments that never ran. As in the first run, these get honest "not reached" outputs. Not fixed here.
- **Producer time.** The first run's edit ran for 94 s and hadn't finished when D1 cut it off. A producer turn over 300 s is an uncertain send (Change 5). This risk is accepted, because the cap is fixed in code.

## Assumptions

- **A1 (confirmed live in `v8-live-validation`).** The CLI exposes `execute-chartered-job`, `decide-expansion`, `inspect-delivery` and `recover-delivery-lead` with the documented flags. v0.36.1 must be installed before `start-plan`.
- **A2 (confirmed again by architecture review S2, with a gap: ledger key `job-charter-sealed-digest`).** Prepare accepts the job charter through the manager assignment's `input_evidence`, without a `job_charter` artifact. The job charter isn't covered by the sealed digests, so its sha256 is recorded at `approve-plan` and in the evidence (A7). The sealing gap is a follow-up, not fixed here.
- **A3.** Magentic's call pattern is about 6 calls when the first review passes, and more with a retry. This comes from the MAF-gated tests and the spike. If Magentic finishes in 4 calls or fewer, neither event happens, and R6 applies.

## Open questions

- **Producer time budget (closed by architecture review I2).** Measured from the first run, manager calls took 21.0, 9.2 and 12.2 s. The first launch is estimated at about 250 to 430 s, inside the 600 s deadline, and the deadline is recoverable (Change 5).
- **Base delegations.** A retune for a second attempt must keep base delegations at 2 or more, because prepare refuses a roster larger than the base. Retuning therefore adjusts only the manager-call base and headroom.
