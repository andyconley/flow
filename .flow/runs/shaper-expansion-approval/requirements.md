# Requirements: Shaper expansion approval (MAF adoption step 5, slice 1)

- **Status:** revised after adversarial review (`adversarial-review.md`), awaiting engineer approval.
- **Owner and approver:** Andy, Flow's only user. Backwards compatibility is not required.
- **Parent design:** `docs/maf-adoption-design.md`, adoption step 5.

## Problem

- **What:** a chartered v8 Delivery Lead (stock Magentic under Flow's gateway) that hits a charter limit is denied outright. The ledger returns `delegation_cap`, `paid_call_cap`, `verifier_call_cap`, `manager_call_cap` or `manager_round_cap`.
  - A denied specialist call is reported to the manager.
  - A denied manager call ends the attempt as failed.
  - Nobody is asked, and nothing records what the lead wanted or why.
  - The charter's `scope_expansion: "halt_for_shaper"` is a label with no mechanism behind it, and `delegated_expansion` must be `false` (`cli/delivery_contracts.py`).
- **Who:** Andy, as the Shaper who approves charters and the only operator.
- **Why now:**
  - Steps 1–4 are done, and v8 execution, recovery and a working local verifier shipped in v0.35.2.
  - Step 5 makes the Shaper a delegate rather than a gate that says no.
  - Andy chose to build step 5 before real-world v8 runs.

## Desired outcome

When a Delivery Lead needs more than its charter allows:

- Flow pauses the attempt cleanly and records a structured, Flow-computed expansion request.
- A request within headroom Andy pre-approved at charter time is approved automatically, by fixed rules.
- Anything else waits for Andy's decision from the CLI.
- The attempt then resumes. On approval, Flow re-issues the paused proposal under the grant. On denial, the denial is reported to the manager.
- No model or provider output ever grants authority or sets an amount.

## Engineer decisions (2026-09-25)

- **D1, the approval model:** fixed-rule headroom first; beyond that, Andy decides. A model recommendation is deferred: Andy sees the manager's rationale and Flow's facts.
- **D2, what is expandable** (revised by E1 and E2): delegations, paid worker calls, manager calls, manager rounds, and verifier calls up to the contract ceiling of 2.
  - Replans and the optional specialist pool are deferred.
  - **Never expandable:** write paths, providers, prohibited capabilities, concurrency, runtime and acceptance. These stay hard denials and are never escalated.
- **D3, while waiting:** the attempt stops cleanly and resumes. There is no long-running blocked process.
- **D4, where decisions are made:** the CLI only in this slice.
- **D5 and D7, scope** (revised by E3): headroom, automatic grants and manual grants are all scoped to the **delivery lineage**, meaning the attempt plus any attempts that supersede it. This matches the existing paid-call and verifier caps. Resume keeps the same attempt.
- **D6, after a denial:** the attempt resumes with the denial reported to the manager, which may still finish within the charter.
- **D7, headroom:**
  - Headroom is sealed in the Delivery Charter from the Shaper intent at `start-plan`. The default is zero, so every request escalates.
  - Automatic approvals draw down headroom.
  - Manual grants don't use up headroom. They are recorded separately as Andy's authority.
- **E4, runner ceilings:** base, plus headroom, plus all grants must stay within the MAF runner's hard ceilings. Those are 12 manager calls, 6 manager rounds (also stock Magentic's `max_round_count`), and 6 actions. This is validated at sealing and at every decision.

## Requirements

1. **Headroom in the contract.**
   - The Shaper intent may declare non-negative integer headroom for each expandable limit (D2). The Shaper Contract and Delivery Charter seal it at `start-plan`.
   - Omitting it seals zero.
   - `delegated_expansion` is no longer forced to `false`. The sealed headroom record governs automatic approval.
   - Sealing refuses:
     - a negative value or an unknown limit;
     - verifier headroom that would take the total above 2;
     - any base + headroom above a runner ceiling (E4).
2. **Expansion request.**
   - When an expandable limit denies a v8 Delivery Lead proposal, Flow records an expansion request. It is keyed uniquely on the denied ledger row (attempt, kind, row ID), so recording it again returns the same request.
   - Flow computes everything bound into the request:
     - the run, attempt, lineage and owner generation;
     - the denied proposal and its payload digest;
     - the limit that denied it;
     - the amount, always exactly one unit;
     - the lineage's remaining headroom and current grants;
     - the diff and test evidence digests, if any.
   - The manager's rationale is stored bounded and display-only. It is never parsed into any field, and it is escaped wherever it is shown.
3. **Expansion pause.**
   - Recording a request pauses the attempt through a new stop path. It is distinct from an interruption and from a failed runtime outcome, and nothing is sent for the paused proposal.
   - The lead claim stays `active` at the same generation.
   - `flow run status <work-id>` and `flow run list` show a pending expansion as the run's next action, and `inspect-delivery` shows the request details.
4. **Automatic approval.**
   - If the one-unit request fits the lineage's remaining sealed headroom, and the resulting total stays within the runner ceilings and the verifier ceiling of 2, Flow records an approval under the charter's headroom authority.
   - Headroom is read only from the sealed charter artifact, never from the envelope copy or manager output.
   - The decision is deterministic and idempotent. A crash between request and approval draws headroom once.
5. **Escalated decision.**
   - Otherwise the request waits, and Andy approves or denies it with a CLI command. The command:
     - requires the request ID and the expected owner generation;
     - records his declared identity, an explanation and the decision;
     - approves at most the one unit requested.
   - The command takes the ADR 0016 locks and refuses unless the attempt is truly paused: no action or manager call is `started` or `unknown`, the recovery lock is free, and no supervisor child is alive.
   - It also refuses a manual grant that would go above a runner ceiling or the verifier ceiling of 2.
6. **Resuming.**
   - After a decision, the attempt resumes at the same generation through a recovery mode for the expansion pause.
   - **On approval:** the denied row is marked superseded by the grant (never rewritten), and Flow re-issues the paused proposal itself as a pending action under the grant. Magentic is not asked to propose it again. Each grant is consumed by exactly one allowed decision.
   - **On denial:** the manager receives the denial and continues within the charter.
   - A denied request can't be decided again. A later proposal of the same kind is a new request, keyed on its own denied row.
7. **Scope of a grant.**
   - A grant raises only its own limit, within its delivery lineage.
   - Grants are cumulative within the lineage.
   - Automatic grants never exceed the sealed headroom, and manual grants never touch it.
   - A superseding attempt inherits the lineage's grants and remaining headroom. Supersede never refills headroom.
8. **Evidence.**
   - Receipts list every expansion request and decision: who or what decided, under which authority, and how much was granted.
   - Receipt validation recomputes effective limits from the sealed charter plus the grants. It rejects:
     - a grant that was added, removed or altered;
     - an automatic approval beyond the headroom left at that point in the order;
     - a grant under the wrong authority;
     - a grant larger than its request;
     - a grant tied to another lineage or generation.
9. **Fencing.**
   - Requests, decisions and resumes validate the owner generation and the lead claim.
   - Deciding, superseding and releasing each check request state inside a single `BEGIN IMMEDIATE` transaction. A race leaves exactly one outcome.
   - A superseded or released lead records a pending request as cancelled.
10. **The v8 boundary.** Protocol v8 chartered attempts only. v5–v7 are unchanged, with no compatibility shims.

## Non-goals (slice 1)

- A model-generated recommendation. It is deferred and would be advisory only.
- Replan expansion. v7 and v8 replans can't be reached today (`decide_replan` accepts protocols 2, 5 and 6).
- The optional specialist pool.
- Making runner ceilings configurable through the envelope.
- Cancellation, stuck-run detection, trace correlation, a cross-project inbox, and diagnostics beyond showing pending requests.
- Making decisions from ChatGPT or over MCP.
- Expanding runtime, concurrency, write paths or providers, lifting prohibited capabilities, or amending acceptance criteria.
- A token or dollar cap.
- Re-sealing or re-versioning the Delivery Charter to record a grant. Headroom lives in fields sealed at `start-plan`, as limits do today.
- A usage metric. Receipts record every request and decision, so counts can be derived later.
- A live end-to-end run. Real-world validation follows once step 5 is complete.

## Constraints

- **ADR 0011 and 0012:** Flow-owned authority and evidence only.
- **ADR 0014:** `run.json` and the sealed charter are the authority chain, and a stale generation is fenced.
- **ADR 0016:** keep the lock order (recovery, run, send, then SQLite), and resume only from bound state.
- Nothing is sent for a paused proposal until a grant exists.

## Assumptions

- **A1 and A2 (original): rejected by review.** They were replaced by R3 (a new pause path) and R6 (Flow re-issues the proposal).
- **A3: confirmed.** The manager call gate runs before send. Round expansion is bounded by the runner ceiling (E4).
- **A4 (new, for solutioning):** the paused proposal can be re-issued Flow-side as a pending action bound to the grant, and the resumed Magentic run will accept that result. A resume-mechanics spike should confirm this first.

## Evidence

- **Code (inspected manually):**
  - `cli/execution_ledger.py`: `decide`, `decide_replan`, the manager call gate, and the lineage-counted caps;
  - `cli/delivery_gateway.py`: the denied reply, `_resume_chartered`, and prepare's check against the sealed charter;
  - `cli/delivery_recovery.py`: eligibility and resume modes;
  - `runtime/maf_runner/delivery_lead.py`: the runner ceilings, and how action and call IDs are formed;
  - `cli/delivery_contracts.py`: intent and charter validation.
- **Archive search** (selection `7eb6c3af…`, complete, 12 matches):
  - `shaper-delivery-runtime-contracts` (disabled expansion): supersession proposed, and approving this definition is the explicit decision.
  - `session-model-recommendation`: adapted. Advice never grants or gates.

## Open questions

- None blocking. A4 is for `flow-solution`.
