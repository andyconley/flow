# Proposed acceptance criteria

Status: **Approved 2026-09-22 by Andy Conley**

- [ ] Flow validates and canonicalizes a runtime-neutral Shaper contract with all required identity, scope, evidence, authority, risk, and amendment fields.
- [ ] Explicit approval creates a sealed Delivery Charter whose digest, source artifact digests, approval, roster, provider capabilities, limits, and verification obligations are inspectable.
- [ ] Flow records an unambiguous Definition-to-Delivery transition; no Delivery Lead can start without it.
- [ ] A Delivery Lead request outside the charter is denied or routed to a versioned amendment. The approved charter is unchanged.
- [ ] One active Delivery Lead per attempt can plan and replan through stock Magentic, while every manager/specialist provider send requires a Flow grant.
- [ ] Before cross-runtime implementation is committed, a bounded feasibility probe establishes the supported ChatGPT Work surface, local artifact access, project/operator binding, and locality limits; its result either defines the adapter acceptance contract or returns the definition for an explicit scope decision.
- [ ] Once that adapter contract is approved, a job shaped in ChatGPT Work can be inspected/refined in Claude Code and planned/delivered in Codex using the same run ID, charter version/digest, artifacts, and lifecycle state.
- [ ] Runtime session transcripts are not required to resume; missing session state does not lose approved decisions or evidence.
- [ ] One bounded real charter-driven job selects from an approved Flow specialist roster, completes provider work, uses an independent verifier where required, and produces a Flow-sealed receipt tied to the charter.
- [ ] Unknown or interrupted provider calls remain fail-closed across runtime changes and require evidence-backed reconciliation before retry.
- [ ] Existing chartered execution records remain readable or produce a clear version/compatibility diagnostic; no destructive migration is required.
- [ ] Malformed, partially migrated, or digest-mismatched legacy records cannot become dispatch-eligible.
- [ ] Replayed approval/transition does not create another charter or active delivery; withdrawal or cancellation before dispatch produces zero provider sends.
- [ ] Concurrent runtime mutations serialize or fail with an actionable stale-state conflict, and an unavailable local worktree binding cannot be treated as portable authority.
- [ ] A compatible provider replacement occurs only when the charter permits the capability and Flow issues a new grant; provider-specific requirements remain pinned.
- [ ] Ordinary Chat MCP ingress and secure tunneling are absent from first-release acceptance.
- [ ] Tests demonstrate zero provider sends for invalid charter, unapproved transition, roster expansion, unapproved provider substitution, duplicate grant, malformed migration, and out-of-charter amendment attempts.
