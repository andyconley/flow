# ADR 0022: Deterministic provider selection outside Shaper authority

- Status: Accepted
- Date: 2026-09-29

## Context

Protocol v8 seals concrete provider and model identities produced during shaping.
That makes delivery depend on the runtime hosting the Shaper and prevents one
auditable local-first policy from governing Magentic, MAF, and the Flow gateway.
Flow already owns dispatch grants and recovery under ADR 0011 and ADR 0012.

## Decision

Protocol v9 will carry logical assignments. Flow will seal logical requirements,
effective policy, an administrator-authorized candidate catalog, normalized
availability, and prior positive no-send evidence. A shared, versioned, pure
selector will run inside the supervised MAF child and independently in Flow.
The child's decision is a proposal; only an identical Flow recomputation may be
granted and sent.

Eligible local Ollama candidates rank before hosted candidates. The default
hosted order is Claude then Codex. Project and approved run policy may narrow
eligibility and reorder surviving hosted candidates, but cannot broaden
administrator restrictions or adapter capabilities. High-risk verification
requires a disjoint provider family unless the exact run seals explicit user
approval for an exception.

Only positive fenced evidence that no provider send began permits fallback.
Once a send begins or becomes uncertain, Flow recovery owns the outcome.
Protocol v8 remains separately validated, read, resumed, and recovered; it is
never reranked through the v9 selector.

Ollama manager and producer support will use dedicated bounded adapters.
Producer models return structured edit proposals; Flow validates scope, paths,
base digests, limits, and the resulting diff before applying any bytes. Models
receive no arbitrary shell or unrestricted filesystem authority.

## Consequences

- Selection decisions become canonical, digest-bound, and offline-recomputable.
- Manager bootstrap is a Flow-side use of the same selector because Magentic is
  not running until its manager has been selected.
- V9 requires additive selection persistence and explicit version dispatch at
  contract, ledger, receipt, inspection, and recovery boundaries.
- Availability discovery establishes presence only. Capability remains an
  administrator-authored, versioned declaration.
- The implementation carries temporary v8/v9 branching rather than risking a
  compatibility rewrite.

## Rejected alternatives

- Hidden concrete provider participants retain provider identity in Magentic
  checkpoints and multiply roster complexity.
- Gateway-only selection does not satisfy independent selection inside the
  supervised MAF workflow.
- Separate child and gateway ranking implementations create avoidable drift.
- Direct model filesystem or shell access weakens Flow-owned mutation evidence.

## Revisit when

Revisit if Magentic gains a provider-neutral executable binding contract, the
selector must be implemented across languages, or a provider supplies durable
exactly-once request identity strong enough to revise uncertain-send recovery.

## 2026-10-01 refinement: authority and semantic completion

The first live protocol-v9 proof showed that internally consistent selection
evidence is not sufficient proof of completed work. The manager had received a
singleton roster, assignment bodies had been reconstructed from IDs, and a
verifier turn that only announced an intention to inspect was accepted as
successful verification.

Protocol v9 therefore also applies these boundaries:

- the approved job charter seals complete provider-neutral assignment bodies
  and dependencies; runtime projection copies them without defaults;
- Flow computes the complete dependency-valid unfinished frontier and Magentic
  selects one member; manager prose is context, not executable authority;
- Flow captures the scoped diff and chartered-test evidence, builds the exact
  verifier input, evaluates the structured response under ADR 0015, and permits
  successful completion only for `valid_pass`;
- hosted editors operate through Flow-controlled scoped staging rather than
  direct workspace-wide mutation; and
- one runtime independence resolver supplies identical family and waiver facts
  to initial selection, fallback, receipt construction, and offline replay.

Direct hosted-workspace access followed by rollback was rejected because it
cannot prevent out-of-scope reads. A new protocol number was also rejected:
v9 remains pre-release and can accept this additive contract refinement while
historical v8 bytes and behavior remain unchanged.
