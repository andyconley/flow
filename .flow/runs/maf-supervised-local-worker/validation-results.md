# Validation results: supervised local MAF worker

## Automated checks

- Focused execution and supervisor suite: `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m unittest tests.test_execution tests.test_maf_supervisor` — 25 passed. Tests use stub providers and fake children; they make no Ollama or paid request.
- Full repository suite: final post-change run passed 1,120 tests, one skipped (`PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -m unittest discover -s tests`).
- `flow run verify maf-supervised-local-worker` — `ok`.
- `flow run execute-local --help` — installed develop launcher exposes the command.
- `scripts/regenerate-flow-help.py --check` and `git diff --check` — passed.
- The active develop install points to this checkout. `flow sync claude --user` and `flow sync codex --user` updated the managed `flow-help` skill; both `--check` commands are now clean. `flow runtime smoke --target all` reports zero static failures and four manual client checks still required. `flow doctor` had earlier reported a retrieval FTS5 preflight issue; it is outside this execution slice.

## Mutation checks

Three deliberate, temporary in-process patches were applied one at a time, without changing source files. Each covering test failed while its control was disabled; the unchanged focused suite then passed 25/25.

1. `ExecutionLedger.consume_grant` forced to return `True`: `test_ledger_grant_is_single_use_and_duplicate_action_is_denied` failed because a consumed grant was reused. This covers bypassing grant validation and reuse.
2. `maf_supervisor._verify_envelope_binding` replaced with a no-op: `test_rejects_finish_before_proposal_and_foreign_attempt` errored when the foreign-attempt proposal reached the callback. This covers attempt binding.
3. `validate_receipt` replaced with a no-op: `test_receipt_rejects_changed_envelope_link` failed because an altered envelope digest was accepted. This covers the receipt link.

## Physical local acceptance

- Command: `FLOW_MAF_PYTHON=/private/tmp/flow-maf-runtime-spike-20260919/bin/python /opt/homebrew/bin/python3.12 -m cli.flow run execute-local maf-supervised-local-worker --assignment test-producer --task-file .flow/runs/maf-supervised-local-worker/local-task-hardening.txt --json`.
- Dispatch orchestration validation passed immediately before this call. The bounded, local-only post-snapshot attempt `44d98b9e0beb4d0d9a59c682b30af299` completed.
- MAF packages: `agent-framework-core 1.19.0`, `agent-framework-orchestrations 1.2.0`. Provider/model: Ollama `llama3.1:8b` at fixed loopback endpoint. Flow observed one physical HTTP response with prompt/evaluation counts 966/51.
- Receipt: `execution/44d98b9e0beb4d0d9a59c682b30af299/receipt.json`. The reviewer independently matched it to the ledger attempt/action, one-use grant, normalized result, envelope digest, all three exact source snapshots and their hashes, and the referenced checkpoint file. This is a Flow-observed local call, not provider attestation or a measure of model answer quality.

## Limits

- The process shares the operator's user account. The child environment omits credentials, but this is not an OS sandbox.
- This slice supports one local `test-engineer` action per attempt. The provider and workflow expansion remain later slices.
