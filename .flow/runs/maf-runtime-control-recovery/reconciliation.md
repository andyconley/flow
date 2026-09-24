# Reconciliation

Date: 2026-09-19. Independent verdict: [review.md](review.md) **approves the bounded research result**, not MAF adoption or a production gate.

| Claim | Disposition | Evidence and limit |
| --- | --- | --- |
| The Flow policy fails closed for unmetered paid providers and enforces cumulative six/three/two limits | Accepted for this prototype | `research/flow_gate.py`, `research/test_flow_gate.py`; completed replans count toward the cap. Only local Ollama is dispatchable. |
| A MAF-originated disallowed specialist request causes zero dispatch | Accepted | `research/execution-result.json`, `research/receipt.json`; Flow recorded a denial and no dispatch row. |
| A live local worker's post-completion checkpoint resumes in another process without a second Flow-recorded dispatch | Accepted | `research/execution-result.json`, SQLite ledger, MAF checkpoint, `research/receipt.json`. Physical Ollama server request count was not independently observed. |
| The worker result was semantically correct and independently attested | Deferred | Model text was reported to Flow and hashed; observer did not inspect/attest its meaning. |
| Recovery during a worker call is safe | Deferred | A crashed/timed-out call leaves an active slot and unknown side-effect outcome. Add failed/unknown state and reconciliation before production. |
| Every Magentic or production Flow dispatch is gated | Deferred | Gate is wired into this scripted workflow only. Make it unavoidable at all runtime dispatch paths before adoption. |
| MAF earns the production Delivery Lead runtime now | Deferred | The local repair passes its slice, but universal dispatch, interrupted-call recovery, complete receipts, and 70% reduction remain open. |

Review suggestions recorded: final `approved_by_flow` is a test response, not a real approval event; the observer pins this captured fixture and should accept paths/commit as inputs in a future repeatable proof.
