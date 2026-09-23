# ADR 0014: Shaper contracts and fenced Delivery Lead ownership

- Status: accepted
- Date: 2026-09-22

## Decision

Flow seals a runtime-neutral Shaper Contract and derived Delivery Charter when
`start-plan` succeeds. The same atomic lifecycle update grants one
generation-one Delivery Lead claim. `run.json` is the authority commit point;
staged contract artifacts without that binding are inert.

MAF may coordinate a chartered roster, but it cannot create authority,
substitute a provider, amend the charter, or accept work. A later runtime
projection carries only the charter facts needed to execute.

## Compatibility and recovery

V6 records remain readable through a dedicated compatibility reader but are
not executable or resumable through this path. The three contract artifacts
have independent versions. A stale generation is fenced at every subsequent
dispatch boundary. Recovery requires an explicit resume or supersede operation;
elapsed time alone may require attention but cannot transfer ownership.

## Consequences

The first irreversible action remains provider dispatch, which happens after
this handoff and must validate the current claim. Recovery before dispatch is
to leave the sealed artifacts as evidence and either explicitly supersede the
claim or abandon the run. This avoids a second lifecycle kernel while making
the handoff inspectable across ChatGPT Work, Claude Code, and Codex.
