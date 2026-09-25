## Scout Summary

### Scope

- **Problem.** A local v8 verifier could not satisfy the strict JSON contract. Its Ollama system message was the full role body, which ends in the role's own markdown `## Output Format`, and the models followed that instead. Planned in `plan.md` and `validation-plan.md`.
- **`cli/verifier_contracts.py`:**
  - `verifier_instructions(role_body)`: a preamble, then the role body with its `## Output Format` section removed (fence-aware, so the template's own `## Review Summary` goes too), then `VERIFIER_CONTRACT_INSTRUCTION`;
  - `VERIFIER_OUTPUT_SCHEMA`, built from the contract constants.
- **`cli/delivery_gateway.py`:** `_default_worker_adapter` sends the derived instructions to a v8 verifier.
- **`cli/local_worker.py`:** a structured-verifier Ollama request sends `format: VERIFIER_OUTPUT_SCHEMA`.
- **Tests:** `tests/test_verifier_instructions.py` (new), and `tests/test_local_worker.py` (request-body test).
- **Docs:** an amendment to ADR 0015. `STATE.md` updated.
- **Deviations from the plan:**
  - **Where the derivation happens.** The plan put it at roster build, in prepare. But the sealed Delivery Charter pins each role's `definition_digest` to the role body, and prepare refuses any other digest (`delivery_gateway.py`, "runtime roster expands the sealed Delivery Charter"). So the roster keeps the sealed body, and the verifier instructions are derived when the call is sent. No ledger record digests the instructions sent, and the derivation is deterministic.
  - **Scout size.** Two behaviour files plus contract constants, which is slightly over scout's single-primary-file limit. The work was shaped in `plan.md` first because the plan gate needs an approved definition.
- **Unchanged:** the evaluator, parser strictness, producer and manager prompts, and v5–v7. Thinking stays at the model default (engineer's choice).

### Validation

- **Full suite:** 1473 OK, 0 skipped, with `FLOW_MAF_PYTHON` set, run through the fail-closed script (`validation/full-suite.log`).
- **New tests:**
  - section removal, including the fenced template, on a fixture and on every shipped role's effective body;
  - a role without the section is kept whole;
  - the schema mirrors the contract constants;
  - replies that satisfy the schema but break contract rules (over-limit summary, a pass with a blocking finding, a fail with no findings) are still `unusable`;
  - a v8 verifier is sent the derived instructions with its sealed digest untouched, while a producer or a v7 verifier keeps the role body;
  - only structured-verifier Ollama calls carry `format`.
- **Mutations** (`validation/mutations.log`; each source restored and checked by sha256):
  - M1, section removal disabled: 13 failures.
  - M2, `format` dropped: the request-body test fails.
- **Live check, against the change itself** (`validation/live-check.log`). Real path: the sealed quality-reviewer body, then `_default_worker_adapter`, then `call_local` to local Ollama at a 60 s timeout, then `evaluate_candidate`. Three runs per case per model:
  - **gemma4:26b:** 6/6 usable and correct (required).
  - **llama3.1:8b:** 6/6 usable and correct (recorded).
  - Before the fix, both models scored 0/4 (`STATE.md` history). The prompt-only and schema-only variants are in `validation/spike.log`.
- **Not run:** a full chartered delivery with a live verifier; hosted verifiers, which the authority rules don't allow.

### Handback

- **Outcome.** A local v8 verifier now works under the strict contract, and the evaluator still decides every verdict.
- **Caveats:**
  - Thinking models such as gemma4 occasionally return an empty reply (1 in 6 in the spike). This fails closed as `unusable` and uses the verifier allowance.
  - The toy diff is easy, so verdict quality on real diffs is untested.
  - The schema needs an Ollama version that accepts a schema-valued `format` (tested on 0.32.1).
- **Capability gap:** a new run cannot enter `start-plan` without an approved definition, so bug-shaped `flow-plan` work has no gate.
