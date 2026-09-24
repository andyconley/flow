# Review: MAF Delivery Lead decision spike

## Review Summary

**Verdict:** REQUEST CHANGES for acceptance or MAF adoption. The exploratory result supports **continue spike** with MAF as the preferred candidate. It does not establish a Flow-enforced, recoverable Delivery Lead runtime.

**Overview:** A real MAF `ConcurrentBuilder` run invoked Codex SDK, Claude Code, and local Ollama with three existing Flow specialist definitions. A local Magentic manager produced a plan-review request, and a separate model-free workflow restored a checkpoint in another process. The evidence is useful, and `validation-results.md` states most limitations candidly. The required cost boundary, dynamic Flow authorization, live recovery, complete receipt, and 70% comparison remain unproved.

### Critical Issues

- [`requirements.md:16`](requirements.md), [`mixed_provider_probe.py:28`](research/mixed_provider_probe.py), [`plan.md:19`](plan.md): The approved rule says to stop a provider before dispatch when this run has neither reliable cost accounting nor an enforceable limit. The Codex branch verifies ChatGPT sign-in but sets no dollar cap and returns token usage rather than cost. The integrated Codex turn and earlier preflights ran anyway. Claude reported $3.264784 across two calls, but total incremental cost cannot be independently bounded from this evidence. **Stop further paid dispatch in this run.** Account for every call, record the rule breach, and mark the paid-budget criterion failed. Before another live probe, use a provider path with a demonstrable hard cap or keep Codex unproven under the approved rule; a subscription login alone cannot close the $10 accounting gap. The one-task-per-provider deviation also needs explicit disposition.

- [`maf_delivery_probe.py:34`](research/maf_delivery_probe.py), [`mixed_provider_probe.py:87`](research/mixed_provider_probe.py), [`magentic_plan_probe.py:18`](research/magentic_plan_probe.py): The Flow envelope is checked in a standalone pre-dispatch function; the live workflow only asserts participant count, and the Magentic plan-review request is never authorized through Flow. No cumulative ledger or Flow event records a runtime-originated denial. A later MAF delegation could therefore bypass the stated six/three/two envelope. Route every initial and runtime request through one Flow-owned evaluator with cumulative counters and a recorded allow/deny decision, then prove that a denied request causes zero provider dispatch. Until then, acceptance criterion 1 fails as an integrated control.

### Important Issues

- [`restart_probe.py:25`](research/restart_probe.py), [`mixed-provider-result.json:16`](research/mixed-provider-result.json): The two-process checkpoint test restores a model-free approval request, not the live three-provider workflow. Its `denied_by_flow` response is a literal string, with no Flow run reconciliation or worker dispatch ledger. This cannot establish no duplicate work or lost evidence after a live restart. Once the cost boundary is repaired, checkpoint the same bounded workflow after dispatch and reconcile checkpoint ID, provider session IDs, Flow decisions, and dispatch IDs in a second process. Record whether each side effect ran exactly once; otherwise retain this criterion as failed/partial.

- [`observe_receipt.py:21`](research/observe_receipt.py), [`receipt.json:9`](research/receipt.json): The observer independently checks specialist digests and a clean fixture Git HEAD, but imports provider/session metadata from a sanitized result. It does not independently observe actions, validation, checkpoint, or a final worker commit. It also copies the charter digest without recalculating it. `provider_result_attested: false` correctly signals this limit. Build a receipt from Flow-side dispatch events plus an independently observed fixture delta, check result, and final commit; link the checkpoint and recalculate the charter digest. Record unavailable evidence as unknown rather than treating the baseline commit as a worker handback.

- [`mixed_provider_probe.py:28`](research/mixed_provider_probe.py), [`mixed_provider_probe.py:83`](research/mixed_provider_probe.py): The Codex wrapper accepts `completed` status and emits `codex-complete` without checking the worker's actual answer. Thus the workflow result proves invocation, not that Codex followed the shared charter or read the fixture file. The Claude and Ollama branches compare exact answers. Capture a bounded Codex result item and validate its answer, while retaining the separate read-only sandbox and denial settings. Do not rerun a paid provider under the current budget rule merely to fill this evidence gap.

- [`validation-results.md:31`](validation-results.md), [`acceptance-criteria.md:8`](acceptance-criteria.md): The machinery table lists MAF features and remaining Flow work, but provides no denominator, weights, effort estimate, or independent review to substantiate the roughly 70% target. Produce a component-level native-versus-MAF work breakdown with assumptions and ranges for planning, delegation, concurrency, handoff, recovery, tracing, provider bridges, Flow policy, and reconciliation. Assess the percentage from that breakdown; continue to label it unproven until then.

- [`requirements.md:7`](requirements.md), [`mixed_provider_probe.py:20`](research/mixed_provider_probe.py): Three real definition files were injected and hashed, but their artifact contracts and relevant memory were not exercised, and the workflow did not instantiate multiple copies of one role. Add a minimal shared artifact contract and demonstrate distinct instance IDs for a copied specialist before declaring full definition/artifact reuse.

### Suggestions

- [`research/decision.md:1`](research/decision.md): This file accurately describes the first research pass but still reads as the current decision and calls for the live workflow that has since run. Link the later `validation-results.md` and this review from its opening paragraph, or label it explicitly as historical evidence.
- [`mixed_provider_probe.py:91`](research/mixed_provider_probe.py): The outer 150-second timeout may return while the Codex call remains active in an `asyncio.to_thread` worker. Use a provider-level deadline and a cancellable process/session boundary before treating timeouts as a spend control.

### What's Done Well

- The probe uses a disposable Git repository, existing authenticated environments, read-only Codex sandboxing, denied approval mode, Claude's per-call budget switch, and local Ollama. No production Flow dependency was added.
- Definition hashes match the current three specialist files. The result and receipt explicitly mark untested runtime delegation, missing live checkpoint, and unattested provider results. The validation report also discloses the extra provider calls and the cost-rule violation.
- The proposed decision to **continue spike without adopting MAF** follows from the evidence and preserves the freeze on a Flow-native DAG, scheduler, checkpoint system, and broad provider abstraction.

### Verification Story

- Tests reviewed: source and stored JSON for the stub envelope, mixed-provider, Magentic plan, restart, and receipt probes. I did not run paid providers. All three stored JSON files parse and all five Python files compile; the three specialist digests independently match repo files.
- Build/runtime checks reviewed: the disposable fixture currently has a clean Git worktree at `f23b769cd00636f11cb06d1c7e52e8b2add9e795`. Stored mixed-provider results report one live concurrent run, but raw provider events and the original terminal transcript were not independently reviewed.
- Remaining risks: unbounded/uncounted Codex incremental cost, dynamic delegation bypass, replay after restart, self-reported provider actions, and an unsubstantiated 70% savings estimate. No commit or PR was part of this prototype, so Conventional Commit review does not apply. Document structure is clear; the stale first-pass decision link is the main clarity issue.
