# Plan: Flow gate and live local recovery

Status: approved scope from Andy's “Do it” instruction, continuing the prior reviewed spike. Research implementation only; no production Flow dependency or paid provider call.

1. Build a run-local Flow policy module with a durable JSON state, append-only event log, and lock. Authorize every request before dispatch, reserve paid hard-cap amounts, count active and total delegations/replans, and prevent duplicate request IDs from dispatching again. Deny Codex when no enforceable hard cap is supplied.
2. Build a MAF workflow that emits a runtime delegation request. An external Flow policy evaluator responds. A denied request terminates with no worker. An allowed request reaches one local Ollama worker using the current Flow test-engineer definition.
3. After the worker returns, MAF requests final review and writes a file checkpoint. Terminate that process. A second process restores the checkpoint and finishes; inspect the Flow ledger to prove the worker was dispatched once.
4. Independently observe the disposable Git baseline/final state and current definition/charter digests, link decision and checkpoint IDs, and write a bounded receipt. Keep worker content as reported, not independently attested.
5. Run focused policy tests, denial path, live process restart, syntax/JSON checks, orchestration checks, and independent quality review. Document any API limit or failed criterion without broad retries.

Cost rule: no paid provider is dispatched in this run. Local Ollama uses `llama3.1:8b`; the paid policy paths are deterministic tests. A production Codex provider remains unavailable until a hard dollar cap or equivalent accounting can be proved.

Roles: coordinator carries lead-developer, test-engineer, and tech-writer work; an independent quality reviewer checks the resulting evidence. The prototype is confined to `.flow/runs/maf-runtime-control-recovery/` and `/private/tmp`.
