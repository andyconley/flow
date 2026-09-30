# Provider selection policy

Flow protocol v9 separates shaping from delivery binding. Shaper artifacts state
logical operation, tier, capabilities, locality, limits, risk, and independence;
they do not select a provider, model, candidate, or ranked roster.

## Authority and precedence

| Field | Merge rule | Lower-layer authority |
|---|---|---|
| candidate allowlist | intersection | narrow only |
| disabled candidates | union | disable only |
| byte, token, and cost ceilings | minimum | lower only |
| provider preference | deterministic order | reorder surviving hosted providers; Ollama remains first |
| adapter operations and capabilities | code/framework ceiling | none |
| provider family | catalog fact | none |
| independence waiver | absent by default | approved run amendment with sealed user approval only |

Framework policy is followed by administrator, project, and approved run policy.
The result records field provenance and a canonical digest. Mere presence in
Ollama `/api/tags` never grants a capability.

## Selection order

The selector excludes candidates using controlled reason codes, then assigns a
total rank tuple to every survivor. A qualifying local Ollama candidate comes
first. Hosted candidates follow the configured order, Claude then Codex by
default, followed by cost class and stable candidate ID. Input ordering has no
effect on canonical output or the decision digest.

Unknown, stale, or unavailable readiness is ineligible. Previous candidates may
be excluded only by positive no-send evidence. Provider-family filtering occurs
after base eligibility for high-risk verification.

## Runtime path

New chartered jobs use protocol v9. The Shaper supplies a logical assignment;
Flow loads the administrator-authorized candidate catalog, takes a bounded
credential-free readiness snapshot, and seals both with the effective policy.
The supervised MAF child can nominate only the logical assignment and task.
Flow independently recomputes the concrete binding, reserves it in the ledger,
rechecks readiness, claims the send durably, and only then calls the adapter.

```text
approved logical charter
        |
        v
Flow policy + catalog + readiness seal
        |
        v
MAF logical nomination -> Flow recomputation -> ledger reservation
                                                |
                           pre-send refusal -----+---- ready
                                  |                    |
                          successor decision      atomic send claim
                                                       |
                                               adapter + receipt
```

The selection state machine is:

```text
computed -> reserved -> consumed -> completed
                    \-> pre_send_refused -> superseded -> successor computed

consumed -> unknown -> reconciliation required -> cancel or abandon
```

`flow run provider-selection-probe WORK_ID --json` shows the effective policy,
catalog, bounded readiness facts, exclusions, ordering, and selected binding.
It is read-only and never creates an attempt or calls a provider. Local Ollama
readiness requires the exact configured model to be discovered. Hosted
readiness proves only that the bounded local CLI adapter exists; authentication
or entitlement failures occur after the durable send claim and therefore enter
recovery rather than automatic fallback.

Only an availability refusal proven before the send claim advances to the next
eligible candidate. Once any adapter call starts, a failure or lost response is
uncertain and cannot fall forward automatically.

## Operator actions

- `flow run execute-chartered-job` starts a new v9 chartered job.
- `--legacy-v8` is an explicit compatibility route for historical v8 execution contracts.
- `flow run verify-receipt`, `trace`, and `inspect-delivery` dispatch by receipt protocol and expose v9 selection lineage.
- `cancel-delivery` and `abandon-delivery` seal v9 terminal evidence without replaying an uncertain send.
- V9 recovery never resends a claimed call. Inspection reports the unresolved action that must be reconciled or terminated.

## Compatibility matrix

| Capability | Protocol v8 | Protocol v9 |
|---|---|---|
| Shaper artifact | concrete provider roster | logical requirements only |
| Provider selection | sealed historical binding | Flow-owned deterministic binding |
| Receipt verification | unchanged v8 verifier | selection and ledger closure recomputed offline |
| Trace and inspection | existing call/grant lineage | logical action, decision, fallback, and provider action lineage |
| Resume | existing checkpoint behavior | no replay of a claimed send; reconcile or terminate |
| Cancel/abandon | existing process-control path | send-lock terminal seal preserving uncertain evidence |
| Re-ranking | never | only before send from sealed inputs |

## Activation and rollback

V9 is the default only for newly executed chartered jobs. Historical v8
attempts remain readable and recoverable through their existing code paths.
If a v9 rollout must be stopped, disable or narrow candidates in Flow policy;
do not rewrite receipts or re-rank existing attempts. Use `--legacy-v8` only
for an already approved historical v8 contract, not to bypass a v9 denial.

## Compatibility

Protocol v8 retains its concrete roster, provider choice, receipts, inspection,
resume, and recovery behavior. Protocol v9 selection types and evidence are
additive; v8 records are not migrated or interpreted through v9 policy.
