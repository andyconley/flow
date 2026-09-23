# Platform architecture review

## Durable decisions

- Keep Shaper Contract and Delivery Charter as Flow domain records; treat execution envelopes, checkpoints, sessions, and paths as projections or observations.
- Version artifact schemas, execution protocol, and ledger schema independently.
- Use `{run_id, charter_id, charter_version, charter_digest}` for charter identity and `{attempt_id, owner_generation}` for active delivery identity.
- Reuse recovery generation fencing, adding explicit lead actor/runtime and resume/supersede lifecycle events.
- Use a tolerant v6 reader with explicit read/execute/resume capability flags; never rewrite legacy evidence in place.

## Hidden coupling to avoid

V6 currently hard-codes the job contract, Python unittest command shape, provider/capability mappings, roster limits, producer/verifier providers, and equality of allowed/write paths. `prepare_chartered_delivery` also mixes lifecycle lookup, charter construction, provider binding, baseline/test policy, worktree observation, and attempt creation. The new design separates domain validation, execution projection, and dispatch.

## Required ADR

Record the Shaper-to-Delivery boundary, canonical artifact ownership, generation-fenced lead claim, amendment epoch, and v6 inspection-only policy as a durable ADR referencing ADR 0011 and ADR 0012.
