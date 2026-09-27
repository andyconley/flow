# Plan: v8 live validation 3

- **Status:** revised after the architect's plan review (`plan-review.md`: I1–I4 and S1–S8 accepted), pending engineer approval.
- **Inputs:** the approved `requirements.md`, `acceptance-criteria.md` (AC1–AC13), `shaper-intent.json`, `orchestration.json`, `job-charter.json`, `adversarial-review.md` and `definition-dispositions.md`.
- **Base:** adapted from `v8-live-validation-2/plan.md`, whose runbook and scripts are reused. Only the differences below change.
- **Authority:** sealed at `start-plan` on 2026-09-27 against the installed v0.38.0.
  - A v3 charter, `756f6503…2b98`, with the lead claim at generation 1.
  - The limits: delegations 2, concurrency 1, 4 manager calls, 6 rounds, 1 paid worker call, 1 verifier call, 0 replans and retries, 600 s runtime.
  - The headroom: delegations 1, manager calls 1, paid worker calls 1, verifier calls 1.
  - The specialist digests (`tech-writer` `9daf3e0f…`, `quality-reviewer` `1ee52e24…`) equal the installed CLI's, checked on 2026-09-27.

## Planning decisions (proposed defaults; engineer to confirm)

1. **Job, worktree and test.**
   - Reuse `~/src/flow-v8-live-job-2` on `job/decide-expansion-docs-2`, at the job commit `d6d771f2eccdcdd4a0ab43b9691b8cf8f92823a2`. That commit holds run 2's test, whose contract proof already passed.
   - No new job commit, and no test change.
   - The job charter is byte-identical to run 2's: sha256 `fef217325168cf4fbe378f605a006d4315bbebb98af106cd7e9c8ce943fdf798`.
2. **Decision gate,** as in run 2:
   - I present each pending request: its limit, its rationale (escaped), and the headroom left;
   - Andy replies approve or deny;
   - I run `decide-expansion --actor andy` with his words.

   Manager-call escalations default to approve, but each is still decided live.
3. **Launch gate.** A go/no-go follows the preflight, before any paid call. A successor launch gets its own go.
4. **Verifier gate (plan review I1).** From `~/src/flow`, after warming the model with `keep_alive: -1`:
   ```
   /opt/homebrew/bin/python3.12 .flow/runs/v8-live-validation-3/scripts/verifier_gate.py .flow/runs/v8-live-validation-2/evidence/attempt-1-worktree.diff .flow/runs/v8-live-validation-3/job-charter.json --limit 30 > .flow/runs/v8-live-validation-3/evidence/verifier-gate[-n].json
   ```
   The diff is run 2's real four-file diff. Go means under 30 s; the script exits 1 on no-go.
5. **Stuck attempts** use the v0.38.0 CLI only (R9). Nothing needs Python except evidence reads.
6. **A completed job's docs diff** becomes its own small PR after the evidence is recorded, as in run 2.

## Binding amendments (from the definition and plan review; replace run 2's)

- **Where N and the working directory come from (plan review I2).**
  - Every `flow run` command runs with the current directory set to `~/src/flow`. `inspect-delivery` has no `--project-root`, and the worktree has its own tracked `.flow`.
  - **For decide, cancel and abandon,** N is the ledger attempt generation: `jq .attempt.owner_generation` from `flow run inspect-delivery v8-live-validation-3 --attempt-id <id> --json`. Cross-check it against `flow run stuck --json`: `.attempts[] | select(.work_id=="v8-live-validation-3") | .owner_generation`. Re-read it right before every command.
  - It is **not** `.delivery_authority.owner_generation`. That is the lead generation, which is used only by `delivery-lead`.
- **Stuck attempts follow `stuck` (plan review S4).**
  - Run `flow run stuck --json`, save it, and run the `next_command` it names for this attempt. That is normally `abandon-delivery`; it is `cancel-delivery` if the parent still reads as live.
  - **Before an abandon (S1):**
    - copy `execution/<id>/receipt.json`, if present, to `evidence/attempt-<n>-draft-receipt.json`;
    - list the attempt directory;
    - save run.json's `delivery` block.

    Save the `delivery` block again afterwards, so that "lead claim unchanged" is a diff.
- **A cancel that times out (S3).** `CANCEL_TIMEOUT` leaves the attempt `started`. Follow `stuck`'s next command, which is normally abandon.
- **Supersede (plan review I4)** has a CLI in v0.38.0:
  ```
  flow run delivery-lead v8-live-validation-3 supersede --expected-generation <lead gen> --owner andy --json
  ```
  - `<lead gen>` is `.delivery_authority.owner_generation`.
  - Supersede moves the lead generation, so a successor's envelope carries a new lead claim.
  - It is not a gap. R6's "has no CLI" is corrected here, because the sealed requirements can't be edited.
  - It is almost never needed, because abandon works under any lead status.
- **Don't leave an attempt started at handback (S7).** If the run stops on the budget or defect contingency, abandon any started attempt through the CLI before `mark-handback-ready`, or record explicitly why it was left.

- **An uncertain send** is `reconciliation_required`, with `resume_available: false`.
  1. Record the signature and the `unknown` row, and classify it under AC8.
  2. Run `flow run stuck`, then `flow run inspect-delivery v8-live-validation-3 --attempt-id <id> --json` to read the ledger `owner_generation` N.
  3. Run `flow run abandon-delivery v8-live-validation-3 <id> --actor andy --explanation "<reason>" --expected-generation N --json`.
  4. Record the output and AC13.

  A successor may follow (below). There is no release call and no Python.
- **The 600 s launch deadline** is a transport interruption with `resume_available: true`. Re-warm Ollama, then run `recover-delivery-lead`. This doesn't use up an attempt.
- **An interrupted attempt that recovery refuses, with no uncertain send:** abandon it the same way, and record the refusal.
- **A successor** follows any terminal predecessor (`failed`, `abandoned` or `cancelled`), with at most one successor. Before launch:
  1. **Save the evidence first (plan review I3),** after confirming that the predecessor is terminal (`.attempt.attempt_status`) and that its groups are gone (`.attempt.control`: 0 alive, or `reaped` in the abandon output). Save:
     - `git -C ~/src/flow-v8-live-job-2 status --porcelain --untracked-files=all` to `evidence/attempt-1-worktree.status`;
     - `git -C ~/src/flow-v8-live-job-2 diff HEAD --binary` to `evidence/attempt-1-worktree.diff`;
     - the untracked files, archived with `git -C ~/src/flow-v8-live-job-2 ls-files --others --exclude-standard -z | tar --null -T - -C ~/src/flow-v8-live-job-2 -czf evidence/attempt-1-untracked.tgz`, or the word "none";
     - the sha256 of each saved file.
  2. Only then run `git -C ~/src/flow-v8-live-job-2 reset --hard d6d771f2 && git -C ~/src/flow-v8-live-job-2 clean -fd`.
  3. Confirm `git status --porcelain --untracked-files=all` is empty and HEAD is `d6d771f2`.
  4. **Check the verifier precondition (R6)** from `inspect-delivery v8-live-validation-3 --attempt-id <pred> --json`:
     - `.attempt.verifier_usage.consumed <= 1` (use `consumed`, not `reserved`);
     - if `consumed == 1`, then `.attempt.expansion.headroom_remaining.verifier_calls >= 1`.

     If either fails, there is no successor.
  5. Check that `flow run stuck` lists nothing for this work id.
  6. Re-run the preflight and get Andy's go.

  Then launch exactly as for attempt 1. Prepare links the predecessor.
  - **Expectations (S2)** come from the predecessor's `.attempt.expansion.headroom_remaining`:
    - `manager_calls` 0: the successor's call 5 escalates. If it is 1, call 5 is granted automatically.
    - `paid_worker_calls` 1: the successor's edit is granted automatically. If it is 0 (the S5 edge case), the edit escalates to Andy.
    - predecessor `verifier_usage.consumed` 0: the successor can still retry the verifier automatically, within the lineage total of 2. Record this as an observation.
  - **Record** the successor's `.attempt.predecessors[].receipt_sha256` (AC10).
- **Cancel** is used only for an operational stop: a runaway call, the wrong model, or Andy's request. Run `flow run cancel-delivery v8-live-validation-3 <id> --actor andy --explanation "<reason>" --expected-generation N --json` from a second terminal, and record the reason.
- **Limits** are the sealed ones for every attempt.

## Runbook

### Phase A: preparation (no paid calls)

1. **Baseline (A8).** In the worktree, run the charter's test argv exactly: `/opt/homebrew/bin/python3.12 -m unittest discover -s tests -p test_decide_expansion_docs.py` (S6).
   - It must fail on the help-source and reference assertions.
   - Confirm `git status --porcelain --untracked-files=all` is empty and HEAD is `d6d771f2…`.
   - Record the job charter's sha256.
2. **MAF interpreter.** Export `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python` for every launch and recover, and check `import agent_framework` before each.
3. **Preflight.** Record each result to `evidence/preflight.txt`:
   - `ollama list`;
   - the warm-up with `keep_alive: -1`;
   - the verifier gate JSON (decision 4);
   - `ollama ps` showing `Forever` right before launch;
   - `claude auth status`;
   - `flow update --check` showing v0.38.0 or later;
   - the specialist digests;
   - `inspect-delivery` (AC1);
   - `validate-orchestration --stage dispatch`;
   - the worktree state (AC2);
   - `flow run stuck` listing nothing for this work id.
4. **Enter implementation:** after `approve-plan`, run `start-implementation`.
5. **Launch gate:** present the preflight, and Andy gives go or no-go.

### Phase B: live execution

6. **Launch** from `~/src/flow` with `FLOW_MAF_PYTHON` exported:
   ```
   flow run execute-chartered-job v8-live-validation-3 --worktree ~/src/flow-v8-live-job-2 --source-commit d6d771f2eccdcdd4a0ab43b9691b8cf8f92823a2 --project-root ~/src/flow --json
   ```
   - Capture the JSON, stderr and wall time to `evidence/launch-<n>.json` and `.stderr`.
   - **Evidence names (S5):** `inspect-pause-<n>.json`, `decide-<n>.json`, `inspect-after-decide-<n>.json`, and `recover-<n>.json` with `.stderr`.
   - Keep `evidence/commands.txt` with the time, the command, Andy's words, the rc and the wall time for each.
   - `execute-chartered-job` and `recover-delivery-lead` exit 1 on a pause, so don't run them under `set -e`.
7. **When it pauses** (`expansion_paused`):
   - capture `flow run status` and `inspect-delivery --attempt-id <id> --json`;
   - present the request;
   - read N from the attempt's ledger `owner_generation` right before deciding;
   - run `decide-expansion … --expected-generation N --actor andy --explanation "<Andy's words>" --json`;
   - capture the inspect output again;
   - re-warm Ollama, and check `ollama ps` and the interpreter;
   - then run `flow run recover-delivery-lead v8-live-validation-3 <id> --project-root ~/src/flow --json`.

   Repeat for each pause.
8. **When it's interrupted,** classify it from the output and ledger:
   - transport or the deadline: fix, then recover;
   - an uncertain send: the amendment above.
9. **When it seals,** capture the receipt path and the final inspect output. Then either decide on a successor (the amendment above) or go to Phase C.

### Phase C: evidence and handback

10. **Timings (AC9).** For each attempt, save `/opt/homebrew/bin/python3.12 .flow/runs/v8-live-validation-3/scripts/ledger_timings.py .flow/runs/v8-live-validation-3/execution/ledger.sqlite <attempt>` to `evidence/attempt-<n>-timings.txt`.
11. **Receipt checks (AC3–AC7, AC13)** through the installed CLI's Python with `ExecutionLedger(path, read_only=True)`:
    - `validate_receipt`;
    - the sealed sha256 matches the file;
    - the `expansion` block and `expansion_state`;
    - replay identity: a paused id completes once, sequences are contiguous, and the paid send counts match the ledger;
    - whether the paused call was a D4 retry;
    - no `local_stub`;
    - for an abandoned or cancelled attempt: uncertain rows are `unknown`, the ledger `owner_generation` is N+1, and the lead claim is unchanged.
12. **AC12:**
    - **D1:** the terminal `result` event, the event-log size next to 1 MiB, 0 `stream_event` records, and no limit errors.
    - **D3:** each verifier's content is non-empty and within 60 s.
    - **D4:** the `manager_progress` block.
    - **D5:** the recover after a grant succeeded.
    - **D6:** the reason text, if a no-edit turn happens.
    - **D7:** the facts line appears in the manager request messages; the delegation text is recorded as an observation.
13. **AC11,** if the job completed:
    - the diff touches only the four files;
    - the targeted test and `--check` are clean;
    - `tests/test_flow.py` passes in the worktree;
    - a diff review is written.
14. **Evidence hygiene.** Delete the Claude CLI `latest` symlinks. After staging, `git ls-files -s .flow/runs/v8-live-validation-3 | awk '$1=="120000"'` must be empty.
15. **Write up:**
    - `validation-results.md`, with every AC9 item and a verdict for each of AC1–AC13 per attempt;
    - output files for every manifest assignment, with honest "not reached" text where needed;
    - `HANDOFF.md`, then `mark-handback-ready`.
16. **Docs PR** (decision 6), if the job completed.

## Contingencies

- **Flow defect (R7):** stop, preserve the evidence, record it, and plan a separate fix run.
- **No escalation in attempt 1:** a valid observation under R4 and R6. A successor is only for a terminal attempt that didn't prove the chain; it isn't launched just to get an event.
- **Verifier gate no-go:** don't launch. Re-warm, check memory and GPU pressure, and re-run. If it still fails, stop and ask Andy.
- **Don't edit `job-charter.json` or any approved artifact** after `approve-plan`.
- **Budget:** stop and ask Andy if an attempt runs past about 30 minutes, or anything looks out of bounds.

## Out of scope

- Flow code changes.
- Retuned limits.
- Codex.
- Staged behaviour.
- The rest of step 5.
- The carried-over gaps.
