# Requirements: MAF Delivery Lead decision spike

Status: approved by Andy on 2026-09-19; derived from the target architecture supplied on 2026-09-19. Paid-model cap confirmed separately at $10 total.

1. Keep Flow authoritative for charter, policy, specialist definitions, budgets, evidence, receipts, and retrieval. Keep MAF replaceable as an execution runtime.
2. Test MAF/Magentic against a Flow-issued charter in a disposable repository. The Flow policy boundary must reject an unauthorized initial or runtime-originated delegation. Initial caps: six total delegations, three concurrent, two replans, and only developer/tester/reviewer roles (proposed Flow mapping: `lead-developer`, `test-engineer`, `quality-reviewer`). Any expansion requires Shaper approval; no automatic paid expansion in this spike.
3. Reuse the repository's specialist definitions and artifact contracts; record definition digests and distinct instance IDs if a role is copied.
4. Exercise Codex SDK/App Server, Claude Agent/Code, and a local inference server in one bounded workflow where each is available. Record a provider-specific blocker as a failed criterion, never as a successful stub substitute.
5. Checkpoint, stop the process, resume, and reconcile MAF and Flow state. No duplicate work or policy bypass may result.
6. Independently observe provider/session IDs, actions, repository delta, checks, and final commit for a Flow execution receipt. MAF's own output alone is insufficient evidence.
7. Compare the MAF bridge and reconciliation effort against the Delivery Lead machinery Flow would otherwise need. Treat the roughly 70% reduction as a target to substantiate with a work breakdown, not an assumed fact.
8. Keep Flow-native DAG, scheduler, checkpoint, and broad provider abstraction work frozen pending the decision.

The [first research pass](research/decision.md) is evidence for definition; it does not satisfy requirements 4-7.

The spike may use the existing authenticated Codex and Claude environments. Total incremental paid-model spend is capped at $10. If a provider does not expose reliable cost accounting or an enforceable limit for this run, stop that provider before dispatch and record the criterion as unproven; do not infer zero cost from a subscription login.
