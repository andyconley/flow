# Validation results: guarded Magentic and interrupted local worker

Date: 2026-09-19. Research prototype only; no paid provider call or production Flow runtime change.

## Observed

- [Flow gate tests](research/test_flow_gate.py) passed. Unknown work remains counted against total/concurrent delegation caps, replay is denied, manual reconciliation is recorded once, completed replans still count, and unmetered paid providers remain blocked. The concurrency mutation check still fails its covering assertion when the cap is deliberately changed from 3 to 4, then restores it.
- A deterministic Magentic manager proposed the guarded `security-reviewer` participant. Magentic emitted a request and received a response; Flow recorded `specialist_denied` and **zero** dispatch rows. The first attempt used the wrong MAF custom-executor message type and produced no policy request; the wrapper was corrected to handle `GroupChatRequestMessage`, and the successful proof ran from a fresh checkpoint.
- A second Magentic workflow proposed `test-engineer`. Flow authorized one local Ollama dispatch. The wrapper observed a nonempty streamed update, wrote its hash and character count, marked the dispatch `unknown`, and intentionally terminated the process with exit code 77. No completion result was invented.
- A separate OS process replayed the same pre-dispatch MAF checkpoint. The stable request ID was recognized as a duplicate; the wrapper returned `manual_reconciliation_required`, Flow recorded that event, and the workflow reached terminal output. The dispatch table still contained one `unknown` row.
- [Flow-side receipt](research/receipt.json) recalculated charter and definition digests, read both MAF plan-review checkpoints, checked SQLite policy events, read the stream marker, and verified the disposable Git fixture remained clean at `f23b769cd00636f11cb06d1c7e52e8b2add9e795`.

## Limits

- The manager is deterministic to make dispatch and replay repeatable. This proves Magentic's participant routing through a Flow guard, not an LLM manager's planning quality.
- The run-local guarded factory is the only participant construction path in this probe. Production Flow/MCP integration and other MAF builder paths are not yet wired to it; the prototype alone cannot make bypass impossible across an application.
- The stable request ID supports one specialist invocation per instance in this bounded run. A production adapter needs a MAF invocation ID that distinguishes legitimate later calls while remaining stable on replay.
- Magentic replanning is disabled in this deterministic manager. The Flow gate counts replans in unit tests, but no Magentic-originated replan has been routed through it.
- The first nonempty Ollama stream update was observed by the wrapper. Server-side request count and model-output semantics were not independently attested. The result is intentionally `unknown`, so Flow must reconcile before any retry.
- No file mutation or worker commit was requested. The Git observer proves a clean read-only fixture, not a commit-bound receipt. The roughly 70% avoided-machinery estimate remains unproven.

## Reproduction

The run used `agent-framework-core==1.19.0`, `agent-framework-orchestrations==1.2.0`, and `agent-framework-ollama==1.0.0b260813` in `/private/tmp/flow-maf-runtime-spike-20260919`, with local Ollama `llama3.1:8b`. Run the policy test, then create fresh denied and interrupted state directories. The interrupted `execute` process exits 77 by design after a streamed update. Never rerun `execute` for an `unknown` request; use `recover` to confirm no automatic dispatch.

```sh
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-magentic-interruption/research/test_flow_gate.py
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-magentic-interruption/research/magentic_guard_probe.py denied-prepare /private/tmp/flow-denied-new
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-magentic-interruption/research/magentic_guard_probe.py execute /private/tmp/flow-denied-new
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-magentic-interruption/research/magentic_guard_probe.py allowed-prepare /private/tmp/flow-interrupted-new
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-magentic-interruption/research/magentic_guard_probe.py execute /private/tmp/flow-interrupted-new
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-magentic-interruption/research/magentic_guard_probe.py recover /private/tmp/flow-interrupted-new
```

`observe_receipt.py` takes the denied and interrupted state paths as arguments. `recovery-result.json` is the captured terminal summary for this run; a fresh reproduction should capture its new recovery summary before running the observer.

The saved recovery summary now names the run, checkpoint, and request ID; the observer verifies all three against the supplied interrupted state before accepting the receipt.
