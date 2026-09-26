# Plan Review: v8-live-validation

- **Reviewer:** architect, read-only, 2026-09-26. The expertise lookup returned `no_match`.
- **Verdict:** feasible, once the fixes below are applied. The reviewer confirmed in code that these pass:
  - the test argv and its working directory;
  - worktree containment and the clean baseline;
  - the `decide-expansion` flags;
  - that recovery never looks at the run's lifecycle state;
  - `--check` at baseline;
  - every Phase C check can be done with existing APIs.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| R1 | blocking | `start-implementation` requires `plan_approved`. | **Accepted.** `approve-plan` runs in `flow-plan` after Andy approves; step 5 says so. |
| R2 | major | `FLOW_MAF_PYTHON` must be set for `recover-delivery-lead` too. | **Accepted.** Export it once for the session, and check the interpreter before each launch and recover. |
| R3 | major | Lineage-counted paid and verifier caps mean a second attempt's producer needs an approved expansion. | **Accepted.** The amendment and budget are corrected. |
| R4 | major | A single producer turn must reproduce the generator's rows byte for byte (a raw `\|`, the same order, two files). | **Accepted.** The test's docstring and messages state the exact contract, and the producer can read the test. |
| R5 | minor | `--expected-generation` is the attempt's ledger `owner_generation`. | **Accepted.** Read it from `inspect-delivery --json` before each decision. |
| R6 | minor | `--source-commit` must be the full SHA. | **Accepted.** |
| R7 | minor | Ollama can go cold during a pause. | **Accepted.** Warm it with `keep_alive: -1`, and again before every recover. |
| R8 | minor | One 600-second deadline covers each launch. | **Accepted.** A runner timeout is an interruption to resume. |
| R9 | minor | Script details: `sys.path`, a read-only ledger, and `change_lead_claim` returns a tuple. | **Accepted.** |
