# Brief: solution premise verification, chunk 2

Run `chartered-delivery-recovery-2`, lane `solution`. Read-only; return findings inline.

## Task

Engineer decision C1 limits chunk 2 to Flow-owned evidence: durable observations and Flow-captured traces, never operator-authored files. Checkpoints stay non-authorizing (ADR 0012). The orchestrator suspects this collapses much of the approved scope. Confirm or refute each claim with `file:line` and a status (observed, inferred, or unverified).

1. **Manager calls.** An unresolved (`started`/`unknown`) manager call never has a Flow-owned response anywhere, because `observe_manager_response` records the result and completes the call in one `UPDATE` (`cli/execution_ledger.py:923-945`). Check every path that writes `manager_calls.result_json` or a `manager_response_observed` event, including the runtime and the MAF runner (`runtime/maf_runner/delivery_lead.py`), for any Flow-owned record of a manager reply that survives while the row stays unresolved.
2. **Actions.** The only resolvable action case is a `response_observations` row (`:1216`) whose `complete()` (`:1220`) never ran: an action left `started` or `unknown` with a durable observation. Check the producer and verifier send paths in `cli/delivery_gateway.py` (`on_action` handling, the worker adapter, and verifier evaluation) for the order of observe, complete, and `record_verifier_evaluation`, and for any other durable, Flow-owned response record.
3. **Traces (A5).** v8 captures no provider trace for its roster. The only trace is v5's `claude-implementer.events.ndjson`; see `_build_receipt` around `delivery_gateway.py:1141`. Check what the codex/claude adapters used by v8 persist.
4. **Worker isolation (A4).** Can a worker that Flow launches (a codex or claude producer) write to `.flow/runs/<id>/execution/` or invoke `resolve-execution`? Check the worker sandbox and cwd settings.
5. **The verifier observed-but-unevaluated case.** Is a verifier with a durable observation but no evaluation already handled by chunk 1's boundary (f)? If so, reconcile adds nothing for verifiers.

Then state the actual resolvable set under C1, and which approved requirements (`requirements.md` 1–11) become empty or trivially small.

## Evidence inventory

- `.flow/runs/chartered-delivery-recovery-2/requirements.md` (approved; C1–C3; Q3–Q5), `acceptance-criteria.md`, and `adversarial-review.md`.
- `docs/adr/0012-flow-owned-maf-recovery.md`, `docs/adr/0016-chartered-v8-recovery.md`.
- `cli/execution_ledger.py`, `cli/delivery_gateway.py`, `cli/delivery_recovery.py`, `runtime/maf_runner/delivery_lead.py`, and the provider adapters (`call_codex` and `call_claude`, wherever they are defined).

Keep it under ~700 words.
