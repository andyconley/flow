# Validation results: Flow gate and live local recovery

Date: 2026-09-19. Scope: follow-up research prototype only; no paid provider call or Flow production runtime change.

## What passed

- [Policy tests](research/test_flow_gate.py) passed for total delegations (6), concurrent active delegations (3), replans (2), specialist allowlist, hard-cap validation, cumulative $10 reservation, duplicate request IDs, and one-time dispatch. Unmetered Codex and Claude were denied because no reviewed dispatchable hard-cap adapter is registered. A test-only metered adapter checks budget arithmetic but is explicitly non-dispatchable.
- The mutation check raised the concurrency limit from 3 to 4 in a temporary in-memory test and the covering assertion failed, then restored the limit. This confirms the test can detect a broken concurrency bound.
- [Execution results](research/execution-result.json) record three separate processes: denied MAF-originated specialist request (zero dispatch), authorized local Ollama worker (one dispatch, post-worker checkpoint), then resume (terminal output, dispatch count still one, replay denied).
- [Flow-side receipt](research/receipt.json) independently read the SQLite policy events, MAF checkpoint, current specialist definition digest, charter digest, and disposable Git fixture at `f23b769cd00636f11cb06d1c7e52e8b2add9e795`. It found a clean worktree, one Flow-recorded live local dispatch, zero Flow-recorded paid dispatches, and no duplicate record after resume. Ollama server call count was not independently observed.
- `flow run validate-orchestration maf-runtime-control-recovery --stage dispatch` passed before the live provider call.

## Scope limits

- The test checkpoint was **after** the local worker returned. A crash during a provider call would leave its dispatch marked started and fail closed; recovery of an interrupted provider session is not proved.
- A failed or timed-out worker has no release/repair path in this prototype; its allowed request keeps a concurrency slot until an operator reconciles the ledger. This is a remaining lifecycle gap.
- The worker was local Ollama `llama3.1:8b`. The result digest is derived from model output reported to Flow; the observer does not independently attest its semantic content. No file change or worker commit was requested, so the Git receipt proves a clean read-only fixture rather than a commit-bound handback.
- The Flow policy is a run-local prototype. It is not wired into the production Flow CLI/MCP boundary or every Magentic internal delegation path. The live workflow explicitly calls it at the MAF request boundary.
- The second-process `approved_by_flow` token is a test response that releases the final MAF checkpoint; it is not a separate Shaper or Flow approval event.
- Paid providers fail closed. This repairs the previous cost-rule breach for this prototype but leaves subscription-backed Codex execution unavailable under a dollar cap. No claim is made that a ChatGPT subscription exposes per-call dollar cost.
- The 70% avoided-Delivery-Lead estimate is still unproven; this slice targeted policy and recovery, not the weighted work breakdown.

The independent [review](review.md) approves this bounded research result, while requiring an interrupted-call reconciliation path and universal Magentic dispatch interception before production use.

## Reproduce without paid calls

Use the disposable Python environment from the prior spike, with `agent-framework-core==1.19.0` and `agent-framework-ollama==1.0.0b260813`. The local Ollama service must expose `llama3.1:8b`. Use fresh state directories when repeating the three processes because request IDs are intentionally not reusable.

```sh
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-runtime-control-recovery/research/test_flow_gate.py
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-runtime-control-recovery/research/live_recovery.py denied /private/tmp/flow-maf-denied-new
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-runtime-control-recovery/research/live_recovery.py allowed /private/tmp/flow-maf-live-new
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-runtime-control-recovery/research/live_recovery.py resume /private/tmp/flow-maf-live-new
```

The observer script uses the specific captured state paths and fixture commit from this run. Reproduction with new paths requires pointing it to the new state and expected fixture commit.
