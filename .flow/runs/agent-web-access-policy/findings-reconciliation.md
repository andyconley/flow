# Findings Reconciliation

## Accepted

- Global capability availability with explicit task-level authorization.
- One reusable semantic capability default translated into native Claude and
  Codex configuration.
- Source-owned per-agent opt-out with a non-empty rationale.
- Explicit rationale when re-enabling an inherited opt-out.
- Fail-closed resolution after framework/user-overlay merge.
- Shared untrusted-content and data-disclosure guidance.
- Configuration-only validation with no claim of live runtime enforcement.
- A reusable boolean capability catalog plus a separately keyed exception
  ledger, resolved after framework/user-overlay agent merge.
- Codex enabled output emits the documented live mode and explicit tool enable;
  disabled output emits the matching disabled mode and explicit false value.
  These are one coupled adapter mapping, not independent policy authorities.
- Every explicit exception requires a rationale, including an intentional
  higher-layer re-enable of a lower-layer denial.
- Shared enabled and disabled guidance is generated centrally rather than
  copied into every agent body.
- Malformed user-overlay TOML fails before sync writes. The former warning and
  framework-only fallback could discard an intended denial under the new
  default-enabled policy; Andy Conley accepted the compatibility change.

## Rejected

- Treating role selection, workflow entry, or a merely useful research
  opportunity as authorization to browse.
- Repeating Claude-native tool names as the cross-runtime domain model.
- Using omission as a Codex denial.
- Editing generated runtime agent files.
- Embedding capability fields directly in replaceable `[[agents]]` records.
- Separate Claude and Codex capability policies.
- A general conditional permission language or provider-payload framework.
- Adding agent skill requirements to this work item.

## Deferred

- Per-task technical capability grants and live delegated web smoke tests.
- Authenticated browsing, arbitrary HTTP, credential forwarding, or private
  network access.

## Open conflicts

- None. The architect's concern about two Codex settings was resolved by
  treating the documented mode and tool flag as one invariant adapter bundle;
  structural tests reject contradictory output.
