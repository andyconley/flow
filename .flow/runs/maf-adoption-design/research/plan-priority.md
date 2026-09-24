## Product Decision Summary

### Opportunity

- Problem: Flow has an accepted MAF adoption shape but no production boundary that can start a supervised runtime while retaining Flow's lifecycle, policy, and evidence authority.
- Users: Andy and Flow operators first; the initial worker is a bounded local specialist, with later value for Shaper-initiated work and the existing specialist roster.
- Why now: The design and spikes identify the control seam. A small vertical slice turns that seam into a reviewable interface before provider, approval, and ingress complexity accumulate around it.

### Recommendation

- Prioritize: one foundation-and-local-worker slice. It establishes Flow-owned execution records and proves the supervised runner/gateway with one existing local specialist through the Flow CLI.
- Why: It provides an operational path without enabling paid providers or creating a second authority path. It also gives the next recovery and adapter slices stable records to build on.

### Scope

**Slice boundary:** A user starts an already-authorized Flow run through a new CLI execution command. Flow validates an immutable execution envelope, records one attempt and one policy decision, starts a supervised local MAF runner, and permits exactly one allowlisted local specialist invocation through the guarded gateway. The runner returns normalized completion or failure events. Flow writes a versioned receipt that links the run, charter/envelope, specialist definition digest, policy decision, checkpoint reference when present, result/artifact hashes, and final attempt state.

**Milestones and dependencies:**

1. **Execution contracts and storage seam.** Define versioned charter/envelope, execution-attempt, action/grant, runner event, checkpoint reference, and receipt records. Store them under project run artifacts behind a repository module boundary that can later migrate to durable non-file storage. Depend on existing run lifecycle and orchestration-manifest validation; do not make `run.json` a provider ledger.
2. **Gateway and guarded construction.** Add an application service that resolves an existing local specialist definition from the approved envelope and constructs the MAF participant internally. It must reject raw MAF agents/executors, disallowed roles, providers, or actions before process launch. Depend on milestone 1's stable IDs and policy records.
3. **Supervised runner and CLI vertical path.** Add an explicit Flow CLI command that launches an optional local MAF runner, exchanges only versioned request/event records, supervises its exit, and records terminal completion or failure. Run one local guarded worker. Depend on milestone 2; Flow's normal CLI commands remain usable when the optional runtime is absent.
4. **Receipt and acceptance proof.** Seal the receipt outside the worker interface and expose a readable status/result path. Depend on the preceding event stream and existing run handback gates.

**Deferred scope:**

- Multiple workers, parallelism, multi-turn routing, durable replay identity, crash-point reconciliation, and Flow-gated replans.
- Codex and Claude adapters, paid-budget enforcement, and provider-specific usage accounting.
- Shaper delegated-approval UI or workflow, expanded specialist mapping, MCP ingress, remote runners, and a Flow-native scheduler/DAG/checkpoint engine.
- Claims about a 70% Delivery Lead machinery reduction; measure that after the local vertical path exists.

### Risks and Tradeoffs

- Risks: A file-backed first implementation can accidentally become the permanent database; runner events can become a second scheduler; direct MAF construction can bypass the gateway; a local worker can mask provider-cost and recovery failures.
- Tradeoffs: The slice makes the CLI-to-runner protocol real now, which is more work than a pure schema slice, but it proves the chosen packaging boundary. It deliberately leaves recovery and paid routes unavailable until their controls are built.
- Assumptions: An approved run can supply or reference a versioned charter/envelope; at least one current specialist definition can be run locally; the first local invocation can be bounded to a non-production fixture or safe task with no paid provider call.

### Success

- Success metrics: one command reaches one guarded local worker; every execution has an attempt, decision, and receipt; forbidden role/provider/raw-participant attempts make zero worker calls; Flow remains usable without MAF installed.
- Launch or acceptance criteria:
  - Contract serialization and schema-compatibility tests pass without the optional MAF environment.
  - The CLI validates an approved envelope and starts only the supervised local runner.
  - The runner cannot obtain a worker call without a Flow-issued, one-use grant.
  - A successful local run and a runner failure each leave queryable, non-ambiguous Flow records and a receipt/status response.
  - Tests prove raw participant injection, a disallowed specialist, an unapproved provider, and a duplicate grant are denied before any worker invocation.

### Sequencing after this slice

The next slice should add restart-stable action/replan identity and crash reconciliation against this same protocol. Provider adapters follow only after that. Codex, Claude, and MCP remain later consumers of the same Flow gateway rather than alternate execution paths.
