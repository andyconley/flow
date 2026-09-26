# Plan: v8 live validation

- **Status:** approved by the engineer on 2026-09-26, including the plan amendments. Engineer answers 1a–5a (all recommendations accepted).
- **Inputs:** the approved `requirements.md`, `acceptance-criteria.md` (AC1–AC11), `shaper-intent.json`, `orchestration.json`, `job-charter.json` and `adversarial-review.md`.
- **Authority:** sealed at `start-plan` on 2026-09-26: a v3 Shaper Contract and Delivery Charter, and a lead claim at generation 1.

## Planning decisions (engineer, 2026-09-26)

1. **The targeted test** asserts three things: the help entry lists every real flag, `docs/cli-reference.md` has a `decide-expansion` section that mentions `recover-delivery-lead`, and `scripts/regenerate-flow-help.py --check` is clean.
2. **Worktree:** `git worktree add ~/src/flow-v8-live-job -b job/decide-expansion-docs main`, with only the test committed. HEAD is the job commit, and it is clean.
3. **Decision gate:** I present each pending request, Andy replies approve or deny, and I run `decide-expansion --actor andy` with his words as the explanation.
4. **Escalations:** approve manager-call escalations by default, but decide each one live.
5. **Launch and follow-up:** there is a go/no-go gate after the preflight and before the first paid call. If the job completes, its documentation diff becomes its own small PR after the evidence is recorded.

## Plan amendments (binding; they narrow R6 and AC10)

- **A second attempt runs under the same sealed limits.** The Delivery Charter is immutable after `start-plan`, so "retuned limits" isn't possible within this run. Retuning would need a new definition run.
- **A second attempt after a sealed attempt** (completed or failed) needs no supersede: prepare links the terminal predecessor. Paid-worker and verifier usage counts across the lineage (R3). With a paid base of 1 and no paid headroom, the second attempt's producer is denied, and it needs an expansion Andy approves. The verifier needs a unit too, and the first attempt may already have spent the one unit of headroom. Budget one or two extra decisions for a second attempt. Abandoning a paused or interrupted attempt needs a lead change, which has no CLI. It would use `delivery_control.change_lead_claim(work_id, "supersede", root=…, owner=…)` through the installed CLI's Python, recorded verbatim. That gap is recorded at archive.

## Step-by-step runbook

### Phase A: preparation (no paid calls)

1. **Job branch and test.**
   - Create the worktree and branch as in decision 2.
   - Write `tests/test_decide_expansion_docs.py` (a `unittest.TestCase`, with `REPO_ROOT` taken from `__file__`). The producer can read this file but can't run commands, so its docstring and assertion messages state the exact contract (R4):
     - the generator is `scripts/regenerate-flow-help.py`;
     - it emits a row `` | `<invocation>` | <summary> | `` byte for byte, with no escaping (keep the raw `|` in `(--approve | --deny)`);
     - that row goes in both `scaffolds/default/commands/flow-help.md` and `README.md`, at the same position as the entry in `flow.toml`;
     - the reference section is a `### \`flow run decide-expansion …\`` heading running up to the next `##` or `###` heading.

     It asserts:
     - `scaffolds/default/flow.toml` has a `[[help.cli_commands]]` entry whose invocation starts with `flow run decide-expansion` and contains `WORK_ID`, `ATTEMPT_ID`, `REQUEST_ID`, `--approve`, `--deny`, `--expected-generation`, `--actor`, `--explanation`, `--project-root` and `--json` (parsed with `tomllib`);
     - `docs/cli-reference.md` has a heading line containing `decide-expansion`, and its section mentions `recover-delivery-lead` and `--expected-generation`;
     - `scripts/regenerate-flow-help.py --check` exits 0 (run with `sys.executable`).
   - Commit only this file on `job/decide-expansion-docs`: `test: require decide-expansion documentation`. Record the job commit SHA.
2. **Baseline evidence (A8).**
   - In the worktree, run the charter's test command. It must fail on the first two assertions, while the `--check` assertion passes at baseline.
   - Confirm `git status --porcelain` is empty and HEAD equals the job commit.
   - Record the job charter's sha256 (A7).
3. **MAF interpreter.**
   - Confirm `FLOW_MAF_PYTHON` points to a working pinned MAF interpreter (agent-framework-core 1.19.0, orchestrations 1.2.0).
   - Export it for every launch and every `recover-delivery-lead` (R2), because a recover without it would fail after the claim.
   - Check `"$FLOW_MAF_PYTHON" -c "import agent_framework"` before each launch and each recover.
   - The scratch venv is session-temporary, so build a durable one at `~/.flow/venvs/maf` from `runtime/maf_runner/requirements.txt` with python3.12, and use that.
4. **Preflight (P1, A4, A5):**
   - `ollama list` shows `gemma4:26b`;
   - warm the model with `curl` to `/api/generate` (a short prompt, `keep_alive: -1`), and warm it again before every recover (R7);
   - `claude auth status` reports logged in;
   - the installed release is v0.36.0 or later;
   - the specialist digests from the installed CLI equal the sealed ones;
   - `flow run inspect-delivery v8-live-validation` shows the sealed v3 charter and headroom (AC1);
   - `flow run validate-orchestration v8-live-validation --stage dispatch` passes.
5. **Enter implementation.** `approve-plan` is done in `flow-plan` once Andy approves (R1). Then, in `flow-implement`, run `flow run transition v8-live-validation start-implementation`.
6. **Launch gate.** Present the preflight results. Andy gives go or no-go.

### Phase B: live execution

7. **Launch** from `~/src/flow`, with `FLOW_MAF_PYTHON` exported. `<job-sha>` is the full SHA from `git -C ~/src/flow-v8-live-job rev-parse HEAD` (R6).
   ```
   flow run execute-chartered-job v8-live-validation --worktree ~/src/flow-v8-live-job --source-commit <job-sha> --project-root ~/src/flow --json
   ```
   Capture the full JSON output and the wall time.
8. **When it pauses** (`status: expansion_paused`):
   - Capture `flow run status v8-live-validation` and `flow run inspect-delivery v8-live-validation --attempt-id <id> --json`, plus the text view.
   - Present the request to Andy: its limits, the escaped rationale, and the headroom remaining.
   - Take `<N>` from the attempt's ledger `owner_generation` in the `inspect-delivery --attempt-id … --json` output, read right before each decision. It goes up with each recovery; `run.json` doesn't show it (R5).
   - Run `flow run decide-expansion v8-live-validation <attempt> <request> --approve|--deny --expected-generation <N> --actor andy --explanation "<Andy's words>" --project-root ~/src/flow --json`. Run `inspect-delivery` from `~/src/flow`, because it has no `--project-root` option.
   - Capture the inspect output again, then run `flow run recover-delivery-lead v8-live-validation <attempt> --project-root ~/src/flow --json`. Repeat for each pause.
9. **When it is interrupted** (an environmental failure): record the interruption, fix the environment (for example re-warm Ollama or sign in again), then run `recover-delivery-lead`. This doesn't use up an attempt.
10. **When it seals:** capture the receipt path and the final inspect output.

### Phase C: evidence and handback

11. **Receipt checks,** with a script run through the installed CLI's Python. The script puts `~/.flow/source/cli` on `sys.path`, because the modules import flat, and uses `ExecutionLedger(path, read_only=True)` (R9). It checks:
    - `validate_receipt(envelope, receipt)`;
    - the ledger's `sealed_receipt_sha256` equals the file's sha256;
    - the `expansion` block's requests and decisions;
    - `expansion_state`;
    - replay identity:
      - each paused `call_id` or action id later appears once as `completed`;
      - the manager-call sequences are contiguous with no duplicate sends;
      - the paid Claude sends counted from the receipt match the ledger;
    - provider usage from the receipt, and no `local_stub` evidence (AC3).
12. **AC11,** if completed: the worktree diff touches only the four files, the targeted test passes, and the full `test_flow.py` still passes. I write a human-readable review of the diff.
13. **Write `validation-results.md`,** covering everything AC9 lists, with a verdict for each AC (AC1–AC11). Then write `HANDOFF.md` and run `mark-handback-ready`.
14. **Documentation PR (decision 5a):** commit the producer's diff on `job/decide-expansion-docs` and open a small docs PR, separate from this run's PR.

## Contingencies

- **Flow defect** (R7): stop, preserve the evidence, record it, and plan a separate fix run. The attempt's outcome is "Flow defect".
- **No escalation happens** (the manager skips the review): this is a valid observation under R6. A second attempt is allowed if the first sealed; otherwise follow the abandon route described above.
- **Runner timeout** (R8): one 600-second deadline covers the whole Magentic child in each launch. A timeout is an environmental interruption: record it, then resume with `recover-delivery-lead`.
- **Abandoning an attempt:** `change_lead_claim` returns `(ok, run, errors)` and doesn't raise. Check `ok`, and pass `expected_generation`.
- **Job charter:** don't edit `job-charter.json` after `approve-plan`. Its recorded sha256 is its only protection.
- **Budget:** stop and ask Andy if the wall time exceeds about 30 minutes for an attempt, or anything looks out of bounds.

## Out of scope

Flow code changes, retuned limits (see the amendments), Codex, staged provider behavior, and the rest of step 5.
