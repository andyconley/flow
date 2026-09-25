# Research: C1 premise verification (solution-verify, solution-architect)

- **Question:** under C1 (Flow-owned evidence only; checkpoints non-authorizing), what can chunk 2 actually resolve?
- **Method:** read-only code review on `codex/chartered-delivery-recovery-2` (`ef55eb8`). The orchestrator spot-checked `delivery_gateway.py:1345-1372` and `:346-353`.

## Findings

1. **Manager calls: nothing is resolvable (observed).**
   - `observe_manager_response` writes `completed`, `result_json`, and `manager_response_observed` in one transaction (`execution_ledger.py:923-945`). No other path writes `result_json`.
   - On any error, the gateway marks the call unknown and discards the reply (`delivery_gateway.py:1264-1277`).
   - The runner sees a reply only after it is recorded (`delivery_lead.py:201-205`).
   - The adapters persist nothing (`claude_worker.py:141-209`, `codex_worker.py:99-151`, `maf_supervisor.py:458`).
   - **Implication:** requirement 3 is empty and Q5 is moot. The manager parts of requirements 7 and 9 go too. Manager-call blockers are always "abandon only".
2. **Actions: resolvable only from an observation (observed).**
   - The send order is `observe_send`, adapter, `validate_result`, `observe_response` (`:1353`), `complete` (`:1358`), then `_evaluate_verifier`.
   - An observation without completion arises two ways: process death between `:1353` and `:1358` (the action stays `started`), or `complete` raising, which leads to `mark_unknown` (`:1370-1371`).
   - Every observation was validated before it was written.
   - **Implication:** the resolvable set is `started`/`unknown` producer and verifier actions that have a `response_observations` row. Requirements 2 and 6 describe the same case.
3. **Traces: A5 is refuted, but the trace is too weak to rely on (observed).**
   - v8 Claude producers do write `claude-implementer.events.ndjson` (`delivery_gateway.py:1213,1517-1520`; `claude_edit_worker.py:97,156-158`). Codex producers, the managers, and the Ollama verifiers write nothing.
   - The trace is weak evidence:
     - there is no recorded digest, because v8 never seals an uncertain attempt;
     - the file name is fixed and not bound to an action id;
     - the file is created with `O_EXCL`, so a second Claude send in the same attempt collides;
     - it can hold a success result for a call that raised.
   - **Implication:** the trace route serves one narrow window, and only with a new binding. Recommend deferring it.
4. **Worker isolation: A4 is not established (observed gap).**
   - `--worktree` is supplied by the operator. It is checked only for its top level and its commit (`delivery_gateway.py:346-353`); nothing requires it to be separate from the project root.
   - If the main checkout is passed, `.flow/runs/<id>/execution/` sits inside the Codex `workspace-write` sandbox and within reach of Claude `Edit`.
   - The Claude producer has no shell, and the Codex producer does. The live run's `recovery_lock` stops a resolve while the run is live.
   - **Implication:** add a guard that refuses a worktree containing the project's `.flow/`.
5. **Verifier observed but not completed: not covered by boundary (f) (observed).**
   - Boundary (f) covers a verifier that is completed but unevaluated (`:1054-1066`; `test_boundary_f_…` at `tests/test_chartered_delivery_recovery.py:701`).
   - A verifier that is observed but not completed is still refused (`delivery_recovery.py:89-96`).
   - **Implication:** reconcile covers verifiers too. After it, the existing boundary (f) path evaluates the verifier.

## Resolvable set under C1

1. **Observation-backed:** producer or verifier actions left `started`/`unknown` that have a `response_observations` row.
2. **Trace-backed:** a Claude producer only. Recommended deferred.
3. **Manager calls:** none.
