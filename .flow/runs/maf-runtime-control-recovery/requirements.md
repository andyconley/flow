# Requirements: MAF control and live recovery repair

Approved by Andy's 2026-09-19 instruction to fix the cost/delegation gates and rerun a small live recovery test. Continue the target architecture: Flow owns authority and record; MAF coordinates; no production dependency is adopted by this spike.

1. A Flow-owned dispatch policy must persist cumulative total delegations, current concurrency, replans, specialist allowlist, and paid spend reservations. Initial limits remain six delegations, three concurrent, two replans, developer/tester/reviewer roles, and a $10 total paid-model cap.
2. Every initial or runtime-originated MAF worker request must receive a Flow policy decision before provider dispatch. A denial must produce zero provider calls and a durable decision event. Repeated request IDs must not count or dispatch twice.
3. Paid providers must have a demonstrable per-call hard cap and bounded cumulative reservation before dispatch. Subscription-backed Codex lacks such a cap in the inspected SDK and must be denied in this run. Claude may be represented in policy tests with a hard-cap declaration; no paid Claude call is required. Local Ollama has zero paid-model spend and may run live.
4. The live test must use an existing Flow specialist definition and a disposable Git fixture. MAF must checkpoint after the live local worker completes, then a separate OS process must resume and finish. Flow's dispatch ledger must show one provider call, no duplicate on resume, and a linked checkpoint ID.
5. A Flow-side observer must verify the fixture baseline/final Git state, definition and charter digests, policy decisions, worker call count, checkpoint, and result. The receipt must distinguish independently observed facts from worker-reported output.
6. Keep Flow-native DAG/scheduler/checkpoint/broad provider-abstraction work frozen. Do not send further paid-model calls or change production Flow runtime in this follow-up.
