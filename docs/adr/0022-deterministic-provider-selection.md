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

## 2026-10-02 refinement: observed capacity and successor charters

A claimed provider send may fall forward only when the provider adapter
observes a terminal capacity refusal and the bounded transcript proves that no
agent or tool turn executed. Flow closes that action as
`observed_not_executed`, binds the fixed `model_capacity` evidence to the
ledger and receipt, charges zero tokens, excludes that candidate for the
current logical assignment, and recomputes the next binding from the already
sealed catalog and policy. Timeouts, malformed output, transport loss,
unclassified exits, and capacity text after an execution event remain
`unknown`, charged conservatively, and reconciliation-blocking.

Historical v8 authority becomes v9-eligible only through
`flow run migrate-job-charter-v9`. The lifecycle operation requires explicit
user approval, validates a manifest-linked canonical predecessor and a
complete provider-neutral successor, forbids path escape, symlinks, digest
drift, topology changes, and authority expansion, snapshots lineage, bumps the
Delivery owner generation, and registers the successor digest atomically. It
never infers logical assignment bodies or rewrites v8 attempts and receipts.

## 2026-10-03 correction: stock Magentic owns coordination

The relay implementation drifted from ADR 0011: its v9 child returned before
MAF construction and Flow selected assignments, scheduled workers and retried
producer work. That implementation is retired. V9 now constructs one stock
`StandardMagenticManager` and `MagenticBuilder` workflow, with a credentialless
manager proxy and logical guarded participants. Stock Magentic runs the facts,
plan, progress, bounded parsing retries, replanning and final-answer phases and
writes its pending-worker checkpoints. The v8 implementation remains separate:
its concrete roster, action identities and recovery records are not v9 contracts.

Flow independently computes the permitted unfinished frontier for each progress
proposal, verifies the selected task again at the worker callback, recomputes
local-first bindings, and owns every physical send and evidence decision.
Worker failures are feedback to Magentic; Flow does not select the repair turn.
Flow retains the existing one-repair test-failure boundary and refuses further
execution when sealed budgets are exhausted. A final Magentic answer is a
completion proposal; acceptance requires every required assignment, actual
retained scoped diff/test evidence and every independent verifier's `valid_pass`.
The owner generation and retained diff are checked again at final receipt seal.
Scope or budget expansion still requires the existing approval path.

New v9 envelopes project the sealed Delivery Charter's operation and token
limits. Stock manager phases consume authorized manager calls, not free calls.
The ledger checks those caps inside the physical-send fence. Historical v9
limits are retained; resuming an old job does not enlarge its budget.

### Compatibility and continuation

Historical v8 attempts, checkpoints and receipt bytes are unchanged. Historical
v9 relay attempts have no stock workflow to restore. V9 continuation therefore
restarts stock coordination at an observed clean boundary, supplying the
accepted assignment set and preserving all prior actions and evidence. It does
not resend completed workers. A newly observed manager decision is a new gated
call. Each coordination epoch has a separate checkpoint workflow name.

V9 logical action journals retain the original task, sequence and binding
proposal before reservation. On a clean restart, pending positive no-send
selection chains reuse that identity; the stock checkpoint proposal and its
file digest are retained separately in coordination artifacts. An older relay
chain without a journal is reconstructed only when its sealed assignment and
last observed manager record reproduce the exact logical identity; otherwise
it requires explicit recovery. Started/unknown sends remain reconciliation
blocking, with no automatic retry or fallback. Existing terminal receipts are
still validated under their original envelope and are never rewritten.

Coordination checkpoints are provenance artifacts, not authority to send or
accept. This correction uses clean-boundary recoordination rather than arbitrary
v9 checkpoint restoration. Insufficient historical manager/input budgets can
refuse a resume; a successor/expanded authority must use the approved path,
not editing an envelope or checkpoint in place.
