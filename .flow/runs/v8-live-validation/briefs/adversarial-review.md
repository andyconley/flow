# Adversarial Review Brief: v8-live-validation (definition)

Review the draft definition, read-only, and challenge it from your accountable perspective. Return your findings with evidence (file:line) and a recommended disposition for each: requirement changed, acceptance criterion changed, non-goal clarified, assumption confirmed or rejected, or open question.

## Under review
- `.flow/runs/v8-live-validation/requirements.md`, `acceptance-criteria.md`, `shaper-intent.json`, `job-charter.json` (a draft that planning refines) and `orchestration.json`.

## Context
- **Why this run exists.** It is the first live run of a protocol v8 chartered job. Every v8 path so far is proven only with stubs.
- **What it exercises.** Delegated expansion (ADR 0017, merged in PR #37): an automatic grant within sealed headroom, an escalated request that Andy decides with `flow run decide-expansion`, and a resume with `recover-delivery-lead`.
- **The job.** Document the new `decide-expansion` command in four documentation files, proven by a new targeted test committed before the run.
- **Engineer decisions (2026-09-26):**
  - route through definition first;
  - a real documentation job;
  - a failing test committed on a job branch as a clean baseline;
  - `tech-writer` as producer (Claude sonnet) and `quality-reviewer` as verifier (Ollama `gemma4:26b`), with a Claude sonnet manager;
  - up to two unstaged attempts;
  - live defects fixed in separate runs.

## Evidence inventory (what exists; check before claiming absence)
- **Earlier live job (v6/v7) to mirror:** `.flow/runs/maf-charter-job-launcher/job-charter.json` and `orchestration.json`, whose execution assignments are `magentic-manager`, `claude-docs`, `codex-docs` and `local-verifier`.
- **Preparation and gates:** `cli/delivery_gateway.py` `prepare_chartered_delivery`. It requires an implementing revision-2 run, a `job_charter` artifact, manifest execution assignments, a roster no larger than base delegations, and a worktree free of a project `.flow` directory.
- **Expansion:** `cli/execution_ledger.py` (`_expand_locked`, `decide_expansion`), `cli/delivery_recovery.py` (`_expansion_eligibility`) and ADR 0017.
- **Runner:** the ceilings are in `runtime/maf_runner/limits.py`. The call pattern (facts, plan, progress for each round, final) and its identity are in `runtime/maf_runner/delivery_lead.py` and `tests/test_maf_expansion.py`.
- **Intent validation:** `cli/delivery_contracts.py` `validate_shaper_intent`, `validate_expansion_headroom`. The intent in this run validates.
- **CLI:** `cli/flow.py` defines `execute-chartered-job`, `decide-expansion`, `inspect-delivery` and `recover-delivery-lead`.
- **Help tables:** `scaffolds/default/flow.toml` `[[help.cli_commands]]` and `scripts/regenerate-flow-help.py`. `decide-expansion` is not yet documented anywhere, which was checked with grep.

## Focus by role
- **product-manager:** is the outcome worth doing now, is the scope honest, is the pass bar right, and is the budget acceptable?
- **business-analyst:** are the acceptance criteria observable and unambiguous, do the evidence requirements (AC9) cover what Andy needs, and what edge cases (provider failure, Ollama down, auth expiry, a second attempt) are missing?
- **solution-architect:** are the limits and headroom actually sufficient to produce both expansion events given Magentic's call pattern, and are the manifest and roster valid for prepare? Also check the assumptions A1 and A2, the baseline approach, and anything that would make `start-plan`, `approve-definition` or prepare refuse.
