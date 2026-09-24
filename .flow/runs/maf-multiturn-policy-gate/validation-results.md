# Validation results

- Executed `/private/tmp/flow-maf-runtime-spike-20260919/bin/python .flow/runs/maf-multiturn-policy-gate/multiturn_probe.py /private/tmp/flow-multiturn-verified-20260919`; exit 0 and captured `receipt.json`.
- MAF Magentic issued two custom participant calls. Checkpointed workflow state yielded different SHA-256 IDs for sequence 1 and 2; both Flow ledger entries completed.
- Rebuilt the workflow and resumed the checkpoint just before the second call. Flow rejected the same second ID as duplicate; the participant raised `flow_replay_requires_reconciliation`. Request and dispatch counts remained two. This is a fresh builder in the same process, not a separate-process restart.
- MAF called the Flow-gated manager replan three times through its stall path. The first two completed; the third was denied `replan_cap`. No specialist dispatch occurred in this scenario.
- Raw MAF Agent supplied to `guarded_workflow` raised TypeError before build.
- Python compilation passed. Orchestration dispatch validation passed.
- Mutation check: the first probe revealed that returning a bounded duplicate response permitted a fresh manager to continue and dispatch extra calls. Raising on duplicate stopped this; current assertions require no additional ledger entries.
- These specialist responses are deterministic in-process stubs. The gate records `provider=local-stub`; this run makes **zero actual Ollama calls**. Earlier runs separately proved live local Ollama streaming and interrupted recovery. No paid calls occurred.
- Scope limit: this builder is run-local; raw `MagenticBuilder` remains importable and production-wide mandatory construction is not established. Replan IDs use a manager-local counter and need durable restart semantics before adoption. Receipt is not commit-bound. MAF machinery-reduction target is still unmeasured.
