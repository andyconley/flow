# Review: guarded Magentic dispatch and interrupted local call

## Review Summary

**Verdict:** APPROVE the bounded research result. This does not approve MAF adoption or production use of the guard.

**Overview:** An actual Magentic participant request reached the Flow guard. A disallowed specialist received a policy denial with no Flow dispatch row. A local Ollama specialist then yielded a nonempty streamed update before the test process exited; replay from the same pre-dispatch checkpoint required reconciliation and created no second Flow dispatch row.

### Critical Issues

- None within this run's one-participant, local-only research scope.

### Important Issues

- [`magentic_guard_probe.py:90`](research/magentic_guard_probe.py): The request ID is fixed to the run, specialist instance, and `delegation-1`; it does not bind the MAF request content or charter, and a later legitimate call to the same instance would be rejected as a duplicate. Before using this adapter for a multi-turn runtime, derive the ID from a durable MAF invocation identity plus the Flow run and charter, and test that replay keeps the ID while a distinct invocation gets a distinct ID.
- [`magentic_guard_probe.py:132`](research/magentic_guard_probe.py): The factory guards this one builder path, but the application has no boundary that prevents other code from constructing `MagenticBuilder` with an unguarded participant. Before adoption, make the Flow-owned participant factory the only production construction path and test that raw participant injection is rejected.
- [`magentic_guard_probe.py:51`](research/magentic_guard_probe.py): The deterministic manager disables replanning. The SQLite unit test proves the two-replan count, but a runtime-originated Magentic replan has not passed through Flow policy. Route plan changes through a Flow replan decision and test denial at the cap before allowing broader Magentic workflows.

### Suggestions

- [`magentic_guard_probe.py:120`](research/magentic_guard_probe.py): Keep the streamed marker and process exit status as separate evidence. The marker is written by the wrapper and the exit code appears in a sanitized execution summary; a process supervisor log would strengthen the interruption trail.

### What's Done Well

- The `GroupChatRequestMessage` handler calls `decide()` and `claim_dispatch()` before creating the Ollama agent. The denied ledger has one `specialist_denied` request and zero dispatches.
- SQLite transactions keep unknown work counted against the cumulative and concurrent limits. The replayed request remains `unknown`, records `manual_reconciliation_required`, and cannot claim another dispatch.
- The receipt recalculates definition and charter digests, reads the MAF checkpoints and Flow ledger, and checks the disposable Git fixture. It correctly labels physical Ollama request count and model-output semantics as unverified.
- The follow-up recovery summary now carries the run, checkpoint, and work request IDs. The observer matches all three to the supplied handoff and ledger, closing the earlier risk of accidentally mixing runs.

### Verification Story

- Tests reviewed: I ran `test_flow_gate.py`; all assertions passed, including the concurrency mutation check. I did not rerun the intentional crash or call a paid provider.
- Build/runtime checks reviewed: I reran `observe_receipt.py` against the saved denied and interrupted state directories, including after the recovery-identity change. I read both SQLite ledgers, the stream marker, checkpoint readback, and the stored recovery result. The interrupted ledger has one `worker_dispatched`, one `worker_unknown`, duplicate-request denials, and one reconciliation event; the denied ledger has no dispatch. The stored process summary reports exit code 77, but no independent Ollama server log or raw process supervisor trace was retained.
- Remaining risks: This is a run-local prototype with a deterministic manager and one participant. It does not establish universal Flow gating, multi-turn request identity, Magentic replan gating, physical provider call count, or worker output semantics. No production code or commit changed, so Conventional Commit review does not apply. The documents are clear and fit the run artifact structure.
