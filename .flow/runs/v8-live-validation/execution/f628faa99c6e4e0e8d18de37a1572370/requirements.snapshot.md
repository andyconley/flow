# Requirements: v8 live validation (first live chartered v8 job with expansion)

- **Status:** revised after adversarial review (`adversarial-review.md`), pending engineer approval.
- **Date:** 2026-09-26.

## Problem

Every v8 chartered path is proven only with stub providers. That covers the structured verifier (ADR 0015), recovery (ADR 0016) and delegated expansion (ADR 0017). The only live end-to-end job ran on v7, before the final authority corrections. Andy deferred real-world validation until MAF adoption step 5, slice 1 (delegated expansion) was merged. It merged as PR #37.

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
- **R2, manifest.** The orchestration manifest, frozen at `approve-definition`, carries the three implement-lane execution assignments: `magentic-manager`, `docs-editor` and `local-verifier`, with the providers, models and scopes above. It also carries the definition-lane review assignments.
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
  - Per attempt, worst case: 4 manager calls, plus 1 automatic and up to 3 approved manager calls; 1 paid Claude edit; up to 2 local verifier calls; 600 seconds of runtime per launch.
  - Replayed calls are free.
  - Target: about 30 minutes of wall time per attempt, including its resumes and Andy's decisions. The worst case for two attempts is bounded at about 60 minutes (P3).
- **Local setup.**
  - Ollama is running locally with `gemma4:26b`.
  - The Claude CLI is authenticated.
  - `FLOW_MAF_PYTHON` points to the pinned MAF interpreter.
  - `flow` is installed from the merged release (v0.36.0 or later).
- **Isolation.** The worktree is outside the project `.flow` tree. The v8 prepare step refuses a worktree that contains a project `.flow` directory.
- **Preflight (P1, A4, A5), done before each launch:**
  - `ollama list` shows `gemma4:26b`;
  - the model is warmed with one short prompt, because Flow caps an Ollama verifier call at 60 seconds and a cold load can exceed that;
  - `claude` is authenticated;
  - the installed `flow` is v0.36.0 or later (updated 2026-09-26);
  - the specialist digests computed by the installed `flow` equal the sealed ones (verified 2026-09-26: `tech-writer` `9daf3e0f…`, `quality-reviewer` `1ee52e24…`).

## Assumptions

- **A1 (confirmed).** The CLI exposes `execute-chartered-job`, `decide-expansion`, `inspect-delivery` and `recover-delivery-lead` with the documented flags, and v0.36.0 is installed.
- **A2 (confirmed, with a gap).** Prepare accepts the job charter through the manager assignment's `input_evidence`, without a `job_charter` artifact. The job charter isn't covered by the sealed digests, so its sha256 is recorded at `approve-plan` and in the evidence (A7). The sealing gap is a follow-up, not fixed here.
- **A3.** Magentic's call pattern is about 6 calls when the first review passes, and more with a retry. This comes from the MAF-gated tests and the spike. If Magentic finishes in 4 calls or fewer, neither event happens, and R6 applies.

## Open questions

- **Base delegations.** A retune for a second attempt must keep base delegations at 2 or more, because prepare refuses a roster larger than the base. Retuning therefore adjusts only the manager-call base and headroom.
