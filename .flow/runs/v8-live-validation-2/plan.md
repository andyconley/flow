# Plan: v8 live validation 2

- **Status:** revised after the architect's plan review (`plan-review.md`, F1–F7 all accepted), pending engineer approval.
- **Engineer answers:** all recommendations accepted.
  1. The runbook adapts `v8-live-validation/plan.md`.
  2. The verifier gate uses the first run's real diff and must finish within 30 s.
  3. One architect reviews the plan.
  4. Escalations are handled as before.
- **Inputs:** the approved `requirements.md`, `acceptance-criteria.md` (AC1–AC12), `shaper-intent.json`, `orchestration.json`, `job-charter.json` and `adversarial-review.md`.
- **Authority:** sealed at `start-plan` on 2026-09-26 against the installed v0.36.1.
  - A v3 charter, `dcba681b…7f60`, with the R1 limits and headroom. The headroom is manager calls 1, delegations 1, verifier calls 1, and 0 for the rest.
  - A lead claim at generation 1.
  - The specialist digests (`tech-writer` `9daf3e0f…`, `quality-reviewer` `1ee52e24…`) were re-checked against the installed CLI before sealing.

## Planning decisions (engineer, 2026-09-26)

1. **Targeted test.** It keeps the first run's three assertions, and the test code doesn't change (definition I5). Its module docstring is rewritten for the escaped contract (see Phase A step 1).
2. **Worktree.**
   - Create it with `git worktree add ~/src/flow-v8-live-job-2 -b job/decide-expansion-docs-2 main`.
   - `main` must include v0.36.1, so the generator escapes `|`.
   - Commit only the test. HEAD is the job commit, and the tree is clean.
3. **Decision gate.**
   - I present each pending request: its limit, the rationale (shown escaped), and the headroom left.
   - Andy replies approve or deny.
   - I run `decide-expansion --actor andy` with his words as the explanation.
   - Manager-call escalations default to approve, but each is still decided live.
4. **Launch and follow-up.**
   - A go/no-go gate follows the preflight, before any paid call.
   - If the job completes, its documentation diff becomes its own small PR after the evidence is recorded.
5. **Verifier gate (plan review F2, F3).**
   - After warming the model, run `scripts/verifier_gate.py v8-live-validation/evidence/attempt-1-worktree.diff job-charter.json --limit 30`.
   - It builds the request exactly as Flow does:
     - system prompt: `verifier_instructions` applied to the `quality-reviewer` body;
     - user prompt: `_verifier_provider_task` with the charter task and that real four-file diff;
     - the `format` schema and `num_predict` 1024, and no `num_ctx`, because a different context size would force a reload.
   - It adds `keep_alive: -1`, so the gate doesn't reset the warm model's unload timer.
   - **Go** if the call finishes within **30 s**, half of Flow's 60 s verifier cap. **No-go** otherwise: record it, fix the environment, and re-check.

## Plan amendments (binding; carried over from the first run, then extended)

- **Same limits for a second attempt.** A second attempt runs under the same sealed limits. The Delivery Charter can't change after `start-plan`. This narrows AC10's "a supersede successor with retuned limits": it follows the first run's plan amendment and is recorded as a deviation (plan review F7).
- **An interrupted attempt that recovery can't continue, but that has no uncertain send.** Examples are a repeated transport failure, or recovery refusing. Abandon it with `change_lead_claim(work_id, "supersede", root=Path(...), owner="andy", expected_generation=N)`, and check the returned `(ok, run, errors)`. Prepare refuses a new attempt while a sibling is started. A supersede is refused when there is an uncertain send, and the uncertain-send amendment below applies instead (F7).
- **A second attempt after a sealed attempt.** After a sealed attempt (completed or failed), prepare links the terminal predecessor, and paid-worker and verifier usage count across the lineage (R3). The second attempt's producer is therefore denied and needs an expansion Andy approves. The verifier needs a unit too.
- **An uncertain send ends this run's attempts** (definition Change 5, AC8 C1).
  - This covers any provider call that raises before Flow observes its completion, including an adapter timeout (manager over 120 s, producer over 300 s, verifier over 60 s).
  - The call is marked `unknown`, `resume_available` is false, and a supersede is refused.
  - The only route out is release, through `delivery_control.change_lead_claim(work_id, "release", root=Path("~/src/flow").expanduser(), owner="andy", expected_generation=N)` via the installed CLI's Python (plan review F6).
    - `root` must be a `Path`.
    - `owner` is ignored on release.
    - Read `N` from `run.json` `delivery.owner_generation` right before the call.
    - Check the returned `(ok, run, errors)` tuple.
    - Record the call word for word.
  - This work id then can't execute again, so there's no second attempt in this run.
- **The 600 s launch deadline is recoverable** (definition Change 5).
  - It is checked only on runner protocol reads and writes. A call in progress finishes and is recorded.
  - The next protocol step records a transport interruption with `resume_available: true`.
  - Re-warm Ollama, then run `recover-delivery-lead`. This doesn't use up an attempt.

## Step-by-step runbook

### Phase A: preparation (no paid calls)

1. **Job branch and test.**
   - Create the worktree as in decision 2.
   - Copy `tests/test_decide_expansion_docs.py` from the first run's worktree (`~/src/flow-v8-live-job`, commit `c864241`). Keep its code, make the module docstring a raw string (`r"""`) so `\|` raises no `SyntaxWarning` (plan review F4), and replace rule 2 with:

     > 2. The generated tables are produced by `scripts/regenerate-flow-help.py`. It emits one Markdown row per `[[help.cli_commands]]` entry, in `flow.toml` order, as `` | `<invocation>` | <summary> | ``, and it escapes every `|` inside a cell as `\|`. So the row for this command contains `(--approve \| --deny)`, while `flow.toml` keeps the raw `|`. Add that exact row, at the same position (right after the `inspect-delivery` row), to BOTH `scaffolds/default/commands/flow-help.md` and `README.md`. Nothing else in those tables changes.

   - Commit only this file on `job/decide-expansion-docs-2` as `test: require decide-expansion documentation`, and record the full job commit SHA.
   - **Contract proof (no paid calls).** In a scratch copy of the worktree, apply a hand-written reference edit and show all 3 tests pass. The edit covers the TOML entry with a raw `|`, the regenerated tables with `\|`, and the reference section. Then discard the copy. This proves the contract can be met.
2. **Baseline evidence (A8).**
   - In the worktree, run the charter's test command. It must fail on the help-source and reference assertions, while the `--check` assertion passes at baseline.
   - Confirm `git status --porcelain` is empty and HEAD equals the job commit.
   - Record the job charter's sha256 (A7). The charter isn't edited after `approve-plan`.
3. **MAF interpreter.**
   - Export `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python` for every launch and every `recover-delivery-lead` (R2).
   - Check `"$FLOW_MAF_PYTHON" -c "import agent_framework"` before each launch and each recover.
4. **Preflight (P1, A4, A5, AC2, AC9).** Record each result to `evidence/preflight.txt`:
   - `ollama list` shows `gemma4:26b`;
   - warm it with `/api/generate` and `keep_alive: -1`, then run the **timed verifier gate** (decision 5), recording its JSON output (seconds, verdict, token counts);
   - right before launch, `ollama ps` shows `gemma4:26b` loaded with UNTIL `Forever` (plan review F2);
   - `claude auth status` shows the user is logged in;
   - `flow update --check` shows v0.36.1 is current;
   - the specialist digests from the installed CLI equal the sealed ones;
   - `flow run inspect-delivery v8-live-validation-2` shows the v3 charter and headroom (AC1);
   - `flow run validate-orchestration v8-live-validation-2 --stage dispatch` passes;
   - the fresh worktree `~/src/flow-v8-live-job-2` is clean at the job commit, and the first run's worktree isn't used (AC2).
5. **Enter implementation.** `approve-plan` runs in `flow-plan` once Andy approves. Then, in `flow-implement`, run `flow run transition v8-live-validation-2 start-implementation`.
6. **Backfill the first run's timings (definition Change 4).** Run the `scripts/ledger_timings.py` command below and save its output to `evidence/v8-live-validation-timings.txt`. This needs no paid calls.
   ```
   python3.12 .flow/runs/v8-live-validation-2/scripts/ledger_timings.py .flow/runs/v8-live-validation/execution/ledger.sqlite f628faa99c6e4e0e8d18de37a1572370
   ```
7. **Launch gate.** Present the preflight results, including the verifier gate. Andy gives go or no-go.

### Phase B: live execution

8. **Launch** from `~/src/flow`, with `FLOW_MAF_PYTHON` exported. `<job-sha>` is the full SHA of the job commit (R6).
   ```
   flow run execute-chartered-job v8-live-validation-2 --worktree ~/src/flow-v8-live-job-2 --source-commit <job-sha> --project-root ~/src/flow --json
   ```
   Capture the full JSON output, stderr and wall time.
9. **When it pauses** (`status: expansion_paused`):
   - Capture `flow run status v8-live-validation-2` and `flow run inspect-delivery v8-live-validation-2 --attempt-id <id> --json`.
   - Present the request to Andy.
   - Take `<N>` from the attempt's ledger `owner_generation` in that JSON, read right before each decision.
   - Run `flow run decide-expansion v8-live-validation-2 <attempt> <request> --approve|--deny --expected-generation <N> --actor andy --explanation "<Andy's words>" --project-root ~/src/flow --json`.
   - Capture the inspect output again, re-warm Ollama with `keep_alive: -1`, confirm `ollama ps` shows `Forever`, check the interpreter, then run `flow run recover-delivery-lead v8-live-validation-2 <attempt> --project-root ~/src/flow --json`. Repeat for each pause.
10. **When it's interrupted,** classify the interruption from the launch output and ledger:
    - **Transport, or the launch deadline** (`resume_available: true`): record the signature, fix the environment, then run `recover-delivery-lead`.
    - **Uncertain send** (`reconciliation_required`, `resume_available: false`): follow the amendment. Record the signature and the `unknown` row, classify it as a Flow defect or environmental, release the lead, and stop attempting.
11. **When it seals:** capture the receipt path and the final inspect output.
### Phase C: evidence and handback

12. **Timings (AC9).** For each attempt, save the output of `ledger_timings.py` against `.flow/runs/v8-live-validation-2/execution/ledger.sqlite` to `evidence/attempt-<n>-timings.txt`.
13. **Receipt checks (AC3–AC7).** Use a script run through the installed CLI's Python, with `~/.flow/source/cli` on `sys.path` and `ExecutionLedger(path, read_only=True)`. It checks:
    - `validate_receipt(envelope, receipt)`;
    - the ledger's `sealed_receipt_sha256` equals the file's sha256;
    - the `expansion` block's requests and decisions, and `expansion_state`;
    - replay identity:
      - each paused `call_id` or action id later appears once as `completed`;
      - manager-call sequences are contiguous with no duplicate sends;
      - the paid Claude send count matches the ledger;
    - provider usage, and that no `local_stub` evidence appears.
14. **AC12 (the D1 fix holds live).**
    - Record the producer action's terminal status and its `response_observed` event.
    - Record the size of `claude-implementer.events.ndjson` next to the old 1 MiB cap, and the count of `"type":"stream_event"` records, which must be 0.
    - Record that no `output exceeds limit` or trace-limit error occurred.
15. **AC11,** if the job completed:
    - the worktree diff touches only the four files;
    - the targeted test passes, and `scripts/regenerate-flow-help.py --check` is clean;
    - the full `tests/test_flow.py` still passes;
    - I write a human-readable review of the diff.
16. **Remove the first run's worktree (plan review F5).** Do this here in Phase C, never while an attempt is paused. Run it from `~/src/flow`, and tag the first run's job commit first so `validation-results.md` can still cite it.
    ```
    git tag archive/v8-live-validation-job c864241241ab064faf706ab14f09fe7ca9c28daf3c0
    git worktree remove --force ~/src/flow-v8-live-job
    git branch -D job/decide-expansion-docs
    ```
    The partial edit is already saved as `v8-live-validation/evidence/attempt-1-worktree.diff`. Record the commands.
17. **Evidence hygiene (definition Change 6).** Before any commit of run evidence, delete the Claude CLI's `latest` symlink in each attempt folder. Check `git ls-files -s .flow/runs/v8-live-validation-2 | awk '$1=="120000"'` is empty after staging.
18. **Write the results.** Write `validation-results.md` covering everything AC9 lists, with a verdict for each of AC1–AC12. Write output files for every manifest assignment, using honest "not reached" text where needed. Then write `HANDOFF.md` and run `mark-handback-ready`.
19. **Documentation PR (decision 4):** commit the producer's diff on `job/decide-expansion-docs-2` and open a small docs PR, separate from this run's PR.

## Contingencies

- **Flow defect** (R7): stop, preserve the evidence, record it, and plan a separate fix run.
- **No escalation happens:** a valid observation under R6. A second attempt is allowed only if the first sealed.
- **The verifier gate is a no-go:** don't launch. Re-warm the model, check for GPU or memory pressure, and re-run the gate. If it still fails, stop and ask Andy.
- **Job charter:** don't edit `job-charter.json` after `approve-plan`.
- **Budget:** stop and ask Andy if an attempt's wall time goes past about 30 minutes, or anything looks out of bounds.

## Out of scope

- Flow code changes and retuned limits.
- Codex.
- Staged provider behaviour.
- The rest of step 5.
- Fixing the carried-over gaps (`manifest-timeout-enforcement`, `handback-unreached-assignment-outputs`, `job-charter-sealed-digest`).
