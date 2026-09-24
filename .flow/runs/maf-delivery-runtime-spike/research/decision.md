# MAF Delivery Lead runtime spike: first repo-informed pass (historical)

Date: 2026-09-19. Status: historical first pass. The subsequent live results and current decision are in [validation results](../validation-results.md) and the [independent review](../review.md). No Flow production dependency or runtime was changed.

## Decision

**Keep MAF/Magentic as the preferred runtime candidate; do not adopt it yet.** The previous run's recommendation to defer MAF applied only to the narrow first-Codex-worker adapter. It did not evaluate the Delivery Lead architecture in Andy's charter and must not be used as a decision against MAF for that role.

The six architecture exit tests below are not yet met. The next experiment should be a bounded *live* mixed-provider workflow with process-restart recovery and an independently observed Flow receipt. Keep the freeze on a Flow-native DAG engine, scheduler, checkpoint system, and broad provider abstraction while that experiment runs.

## Repo baseline and executable probe

Flow has 13 specialist definitions at `scaffolds/default/agents/*.md`. Its lifecycle and manifest safety live in `cli/runstate.py` and `cli/orchestration.py`; rendering/configuration lives in `cli/render.py`. No general multi-provider Delivery Lead runner was found in `cli/`. The earlier narrow probe lives at `../../execution-provider-receipt-charter/research/reuse-spike.md` (sibling run) and proved a single MAF pending-request/checkpoint path with stubs in one process.

This pass installed into `/private/tmp/flow-maf-runtime-spike-20260919` only:

- `agent-framework-core==1.19.0`
- `agent-framework-orchestrations==1.2.0`
- `agent-framework-claude==1.0.0b260910`
- `agent-framework-ollama==1.0.0b260813`

`agent-framework-orchestrations==1.19.0` does not exist at the package index; orchestration and core have separate version series. [Executable probe](maf_delivery_probe.py) and [bounded result](maf-delivery-result.json) used MAF `ConcurrentBuilder` with three Flow definition files and Codex/Claude/Ollama *stubs*. It ran one fan-out/fan-in and returned all three roles in deterministic order. A Flow-side pre-dispatch evaluator rejected excess delegations, excess concurrency, excess replans, and an unallowed specialist. The JSON records SHA-256 of each reused specialist file. It made zero model or provider calls. The MAF builder's participant IDs must be unique, so multiple copies of one specialist need distinct instance IDs while retaining a shared definition ID.

The local `claude` CLI is installed (2.1.207), Codex CLI reports ChatGPT sign-in, and MAF's Claude integration imports. MAF's Ollama integration imports, but querying the local Ollama endpoint failed (`127.0.0.1:11434`, operation not permitted). These are capability and preflight observations, not a live mixed-provider result. The Codex SDK was inspected in the prior run; MAF core/orchestrations did not provide a named Codex adapter in this pass. A thin Codex bridge remains Flow-owned.

## Exit tests

| Target test | Observation | Status |
| --- | --- | --- |
| Respect Flow delegation envelope | Four external Flow pre-dispatch denials worked before building a MAF workflow. No dynamic Magentic manager delegation was exercised; runtime-originated requests must be routed through the same gate. Paid budget and Shaper expansion were not tested. | Partial |
| Reuse agent definitions and artifacts | Three of 13 repo definitions were loaded and hashed; MAF accepted corresponding stub executors. No actual instructions, memory, charter, or artifact contract were passed to a live agent. | Partial |
| Mix Codex, Claude, local | MAF Claude/Ollama packages import and stub roles mixed in one workflow. Codex needs a bridge; no provider call occurred. | Unproven |
| Checkpoint/resume reliably | Prior stub restored a pending request with a fresh workflow object in the *same process*. No process restart, worker session recovery, or Flow/MAF state reconciliation. | Partial |
| Evidence and execution receipts to Flow | Stub results and definition hashes are present, but no independently observed repository artifact, provider usage, policy decision receipt, or signed/linked handback. | Unproven |
| Remove roughly 70% of otherwise needed Delivery Lead machinery | MAF exposes Magentic, concurrent, handoff, group-chat builders, checkpoint storage, and request events. No Flow-native Delivery Lead implementation or reviewed work breakdown exists to form a defensible denominator; no 70% estimate is claimed. | Unproven |

## Boundary and next proof

MAF can coordinate, but its built-in `max_round_count` and similar controls do not replace Flow's hard delegation, concurrency, spend, specialist, and expansion policy. Flow must authorize every initial and runtime-originated dispatch, own the charter and record, and independently observe evidence. Checkpoint IDs/state must be linked to a Flow run and reconciled after interruption. Provider-specific options and credentials stay behind thin adapters; the installed framework and user data remain separate.

The next bounded proof should use an isolated disposable repository and a small charter: one Codex worker, one Claude worker, and one available local worker, capped at three concurrent and six total delegations, with an out-of-envelope request that Flow denies. Kill and restart the workflow after a checkpoint, resume the same task, and produce a Flow-side receipt tied to input definition digests, allowed actions, provider/session IDs, changed paths, validation, and final commit. Compare the code and state Flow would otherwise need for planning, delegation, concurrency, handoffs, recovery, and tracing against the MAF bridge/reconciliation cost. The architecture decision is **adopt** only if those tests pass and the reduction is credible; otherwise record the failing criterion and choose a bounded alternative without lifting the engine freeze by default.

## Reproduce

```sh
/opt/homebrew/bin/python3.12 -m venv /private/tmp/flow-maf-runtime-spike-20260919
/private/tmp/flow-maf-runtime-spike-20260919/bin/python -m pip install --no-input agent-framework-core==1.19.0 agent-framework-orchestrations==1.2.0 agent-framework-claude==1.0.0b260910 agent-framework-ollama==1.0.0b260813
/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-delivery-runtime-spike/research/maf_delivery_probe.py
```

Official references: [MAF integrations](https://learn.microsoft.com/en-us/agent-framework/integrations/), [Ollama provider](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/ollama), [workflow checkpoints](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints). Installed signatures and executable output, rather than documentation alone, support the local observations above.
