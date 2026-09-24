# Spike claim reconciliation

- Status: resolved for this investigative handback
- Source: [reuse-spike.md](research/reuse-spike.md) and bounded evidence under `research/spike/`

| Claim ID | Status | Disposition | Reason |
| --- | --- | --- | --- |
| `sdk-public-interface` | observed | accepted | Installed 0.154.0 public signatures and annotations are captured in `research/spike/sdk-inventory.json`; they prove interface shape only. |
| `maf-stub-request-checkpoint` | observed | accepted | Installed 1.19.0 stub result and source show one pending request, checkpoint restoration in a new workflow instance, and denial carried through output. No process restart or Codex worker was used. |
| `flow-first-next-probe` | recommended | deferred | The report recommends a direct Flow/Codex live probe as the least-effort next test. Andy approved the earlier conditional solution, but has not accepted this observed spike conclusion as a production engine decision. |
| `real-worker-behavior` | unverified | deferred | Subscription-backed SDK execution, effective sandbox/approval grants, real interruption, worktree changes, and trusted receipt require a later live probe. |

## Material scope difference

The accepted solution proposed a live worker comparison. Andy narrowed this first plan to SDK capability inspection and a MAF stub, then approved that plan. This spike does not claim to satisfy the solution's live exit criteria. The live tests remain owned by the subsequent worker slice.

No material observed/inferred claim conflict remains undispositioned for this handback.
