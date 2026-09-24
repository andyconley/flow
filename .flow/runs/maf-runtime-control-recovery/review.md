# Review: MAF control and live local recovery

## Review Summary

**Verdict:** APPROVE this bounded research result. It does not approve MAF adoption or production use of the gate.

**Overview:** The follow-up closes the prior spike's immediate cost breach by denying all paid dispatches, including subscription-backed Codex, and demonstrates a Flow decision before one local MAF worker. A separate process resumed the post-worker checkpoint without another Flow-recorded dispatch. The receipt now distinguishes ledger records from independently observed provider calls.

### Critical Issues

- None within the approved local-only, post-worker recovery scope.

### Important Issues

- [`flow_gate.py:92`](research/flow_gate.py), [`live_recovery.py:57`](research/live_recovery.py): An allowed worker that times out or crashes before `complete()` remains active indefinitely. This fails closed, but it can exhaust the three concurrent slots and leaves the outcome of a provider side effect unknown. Before production integration, add a durable failed/unknown state, a reconciliation procedure, and a test that resumes after an interrupted call without silently retrying it.
- [`live_recovery.py:24`](research/live_recovery.py), [`validation-results.md:18`](validation-results.md): The Flow check sits in this scripted MAF workflow, not in every Magentic delegation path or the production Flow CLI/MCP boundary. Before adopting MAF as Delivery Lead, make Flow authorization unavoidable for all runtime-originated dispatches and test a denied Magentic proposal with zero provider calls.

### Suggestions

- [`live_recovery.py:127`](research/live_recovery.py): The resumed final review supplies the literal `approved_by_flow` response without a separate Flow review decision event. Rename it as a test response or record a real policy decision before using this pattern for approval handbacks.
- [`observe_receipt.py:48`](research/observe_receipt.py): The observer pins the disposable fixture commit and state paths. Parameterize these for repeat runs so a fresh proof can regenerate its receipt without editing source.

### What's Done Well

- The SQLite `BEGIN IMMEDIATE` decision and dispatch transactions serialize concurrent requests; duplicate request IDs and duplicate dispatch claims are denied. The regression test now confirms completed replans still count against the cumulative two-replan cap.
- The only dispatchable provider is local Ollama. The test-only metered adapter exercises budget arithmetic but cannot dispatch, and unmetered Codex and Claude are denied. This is a sound fail-closed boundary for the current prototype.
- The observer recalculates the definition and charter digests, reads the policy ledger and MAF checkpoint, and checks the fixture's Git state. It labels the model result as reported and the physical provider call count as unobserved.

### Verification Story

- Tests reviewed: I ran `test_flow_gate.py` under Python 3.12 after the replan fix; it passed, including the concurrency mutation check. I also reproduced the pre-fix third-completed-replan escape in a disposable SQLite ledger and confirmed the revised source and regression test close it. I did not run paid providers or repeat the local Ollama call.
- Build/runtime checks reviewed: `observe_receipt.py` passed against the stored live and denied ledgers, checkpoint, and fixture. `git diff --check` passed. The stored `execution-result.json` reports separate denied, start, and resume processes; raw terminal output and Ollama server logs were not independently retained for review.
- Remaining risks: Interruption during a provider call is unresolved; only post-worker recovery is demonstrated. Physical Ollama request count and model-output semantics are not independently attested. No Flow production code, commit, or PR changed, so Conventional Commit review does not apply. The research documents are clear and located in the run-local artifact tree.
