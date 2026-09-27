# Plan Review: v8-live-validation-2

- **Reviewer:** architect, read-only, 2026-09-26. The expertise lookup returned `no_match`.
- **Verdict:** feasible with the current code, with no blocking findings.
  - The runbook's commands and flags match the installed CLI (`cli/flow.py:564-612`).
  - `approve-plan` then `start-implementation` is the right order.
  - Prepare checks only the new worktree (`delivery_gateway.py:401-434`).
- **Coordinator check:** F1 and F2 were confirmed in the installed code (`execution_ledger.py:1420-1421`, `local_worker.py:68-73`).

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| F1 | major | `ledger_timings.py` counted the verifier twice, because a verifier send writes both `adapter_send_started` and `verifier_send_claimed`. The verifier's end is `response_observed`, and `verifier_evaluated` comes after it | **Fixed.** The script counts a verifier action once and records `evaluated_at`. It was checked on the first run's ledger and on a synthetic producer-and-verifier event sequence |
| F2 | major | Flow's Ollama call sends no `keep_alive`, so a gate call built the same way would reset the model's unload timer to 5 minutes. The verifier could then cold-load inside its 60 s cap and cause an uncertain send | **Fixed.** The gate sends `keep_alive: -1`. The preflight and every pre-recover step warm the model with -1 and record `ollama ps` showing `Forever` |
| F3 | minor | The gate prompt wasn't specified | **Fixed.** A new `scripts/verifier_gate.py` builds Flow's exact system and user prompts, `format` schema and `num_predict`, with no `num_ctx`. The 30 s bar stays |
| F4 | minor | A backslash-escaped pipe in a non-raw docstring raises a `SyntaxWarning` on Python 3.12 | **Fixed.** The docstring is raw (`r"""`). Only the docstring changes, so I5 still holds |
| F5 | minor | Deleting the first run's job branch leaves commit `c864241` unreachable | **Fixed.** Tag `archive/v8-live-validation-job` before deleting. The cleanup moves to Phase C, never while an attempt is paused |
| F6 | minor | Release details: `owner` is ignored, `root` must be a `Path`, and N comes from `run.json` `delivery.owner_generation` | **Fixed** in the uncertain-send amendment |
| F7 | minor | AC10's "retuned limits" conflicts with the same-limits amendment, and an unrecoverable interruption with no uncertain send had no route | **Fixed.** The deviation is recorded, and a supersede route is added (refused after an uncertain send) |
