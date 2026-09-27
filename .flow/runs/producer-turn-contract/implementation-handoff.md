# Implementation Handoff: producer-turn-contract

- **Branch:** `codex/producer-turn-contract` from `main`, after v0.37.0 and the merge of PR #43.
- **Read first:** `requirements.md`, `acceptance-criteria.md`, `plan.md`.
- **Only code file:** `cli/delivery_gateway.py`. It covers the chartered facts block in `_execute_prepared_delivery` and `_verify_chartered_edit`.
- **Tests:** `tests/test_chartered_delivery_gateway.py`.
- **Doc:** `docs/maf-adoption-design.md`.
- **Test commands:**
  - `PYTHONPATH=cli python3.12 -m unittest tests.test_chartered_delivery_gateway`;
  - the full suite via `scratchpad/suite-main.sh`, with `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python`.
- **Constraints:**
  - no paid calls;
  - no charter, protocol or receipt changes;
  - the legacy facts text and `_verify_edit` stay unchanged;
  - mutation checks restore from file backups.
- **Done when:** AC1–AC6 are met and the results are in `validation-results.md`.
