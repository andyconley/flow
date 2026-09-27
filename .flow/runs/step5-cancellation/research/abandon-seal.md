# Research: abandoning a stuck chartered v8 attempt

Definition: `step5-cancellation`. Named question: how can a stuck chartered v8
attempt (status `started`, possibly with `started`/`unknown` actions or manager
calls, and no live process) reach a terminal sealed state so a successor may
start, without weakening the existing fences?

Legend: **[O]** observed in source or docs at the cited line; **[I]** inferred
from reading the code, not exercised by a test or live run in this research.
Paths are relative to `/Users/andyconley/src/flow`.

## 1. Seal paths and terminal statuses today

- **[O]** The attempt status column is free text with no CHECK constraint
  (`cli/execution_ledger.py:74-81`). So adding a status needs no DDL
  migration. Validators enforce the allowed values.
- **[O]** `finish_attempt` accepts only `completed|failed|denied|unknown`
  (`cli/execution_ledger.py:2128`). It refuses v8 `unknown`
  (`:2140-2142`). It requires "uncertain rows > 0" to match "status == unknown"
  (`:2143-2147`), so a v8 attempt with any `started`/`unknown` row cannot be
  sealed through it at all. It also requires a written receipt whose
  `lineage_usage`, `expansion` and `manager_progress` blocks equal the ledger's
  (`:2148-2158`), and it stores `sealed_receipt_sha256`.
- **[O]** `_seal_attempt` (`cli/delivery_gateway.py:1681-1704`) closes open
  expansions, builds the receipt, validates it, writes `receipt.json` and calls
  `finish_attempt`, all under the owner fence (`assert_owner`, `:1699`).
  `_build_receipt` derives `unknown` whenever any row is uncertain
  (`:1259`, `:1272-1273`). For v8, the live path never reaches `_seal_attempt`
  when rows are uncertain. It records an interruption and returns `interrupted`
  instead (`:1645-1655`).
- **[O]** Receipt validation allows only `completed|failed|denied|unknown`
  (`cli/execution_contracts.py:857`, `:997`).
- **[O]** The only ledger-only terminal seal is `superseded`, written by
  `seal_superseded_attempts` (`cli/execution_ledger.py:656-699`). It accepts
  `action in {resume, supersede}` only (`:667`). It refuses when **any attempt
  in the ledger** has an unresolved row (`:673-674`). It turns `allowed` grants
  into `not_dispatched/superseded_unconsumed_grant` (`:683-687`), closes
  expansions (`:688`), and sets `status='superseded'`, `receipt_path=NULL` and
  `owner_generation+1` (`:694-696`). It writes no receipt file and no
  `sealed_receipt_sha256`.
- **[O]** Predecessor links accept `completed|failed|denied|superseded`
  (`cli/execution_contracts.py:334`). `receipt_sha256` may be null only for
  `superseded` (`:385-386`). `_v8_lineage_locked` emits a null digest only for
  `superseded` (`cli/execution_ledger.py:361`).
- **[O]** No `cancelled` or `abandoned` **attempt** status exists anywhere. The
  only `cancelled` value is an expansion-request status
  (`cli/execution_contracts.py:392`; `cli/execution_ledger.py:706`).
  "Abandon" exists only as operator guidance text
  (`cli/delivery_recovery.py:37`, `:58-66`) and in the ADRs.
- **[I]** `inspect-delivery` computes `sealed_receipt.consistent` as true only
  when (no digests and status `started`) or (digests match)
  (`cli/delivery_projection.py:85-87`). A `superseded` attempt therefore
  appears to print `INCONSISTENT` (`cli/flow.py:1061`). Any new receipt-less
  terminal status inherits this.

## 2. Reconciliation routes: what an operator can do today

Scenario: v8 attempt `started`, one paid producer action `unknown`, no live
process, lead `active`.

1. `flow run inspect-delivery <work> --attempt-id <a>` **[O]**. Eligibility
   refuses `reconciliation_required` and lists every uncertain row
   (`cli/delivery_recovery.py:184-191`). The row's `evidence_needed` is
   `resolve-execution (stored response)` only if a `response_observations` row
   exists and the instance is a producer or verifier. Otherwise it is
   "unresolvable; abandon only (release, or lifecycle block)" (`:180-182`,
   `:60`). Manager calls are always abandon-only (`:187-188`).
2. `flow run resolve-execution ... resolved_completed --expected-generation N`
   **[O]** (`cli/delivery_gateway.py:1019-1060`). This works only with a
   stored observation (`cli/execution_ledger.py:1794-1795`, else
   `evidence_insufficient`) and a recorded send (`:1812-1813`). It refuses
   manager calls with `unresolvable_abandon_only` (`:1765-1768`), any
   disposition other than `resolved_completed` (`cli/delivery_gateway.py:1032-1033`),
   operator evidence files (`:1028-1029`), and an inactive lead
   (`:1052-1053`). **This is dead end 1 for a lost response.**
3. `flow run recover-delivery-lead` / `continue-resolved-execution` **[O]**.
   The same eligibility refuses `reconciliation_required` before any claim
   (`cli/delivery_gateway.py:684-688`).
4. Lead `resume`/`supersede` **[O]**. There is no CLI: `change_lead_claim`
   (`cli/delivery_control.py:210`) is not wired in `cli/flow.py` (gap
   `delivery-lead-claim-cli`, `~/.flow/user/capability-gaps.jsonl:61`). Even
   through the API, `_fence_and_seal_attempts` refuses on
   `lead_change_blocker()` (`cli/delivery_control.py:302-303`), which scans
   every attempt in the run's ledger (`cli/execution_ledger.py:635-646`).
   **Dead end 2.**
5. Lead `release` **[O]** always passes the uncertainty check "so abandonment
   remains available" (`cli/delivery_control.py:297-300`; ADR 0016:81-82).
   But it only closes expansions (`:310-313`), so the attempt **stays
   `started`**.
6. Preparing a successor **[O]** refuses with `sibling_attempt_not_terminal`
   at prepare (`cli/delivery_gateway.py:430-434`) and again inside
   `create_attempt` (`cli/execution_ledger.py:338-340`). **Dead end 3.** After
   a release, `resume`/`supersede` from `released` is allowed by status
   (`cli/delivery_control.py:249`) but hits the same blocker from step 4.
7. Lifecycle `block` is the only remaining exit, so the work id is dead and
   the live runs had to start a new work id **[O]** for the mechanism; the
   live-run outcome is reported in the intake (`intake.md:27`) and the gap log
   (`capability-gaps.jsonl:52`, `:61`).

Additional dead end **[O]**: ADR 0016 (`docs/adr/0016-chartered-v8-recovery.md:128-130`)
states that a released lead cannot resolve an *observed* uncertain action and
cannot change lead, "so the only remedy is abandonment; this fails closed".
Today "abandonment" means only release or block, which strands the work id.

Note **[I]**: `lead_change_blocker` is run-wide and ignores attempt status.
A v7 attempt sealed `unknown` (allowed for v5-v7 at
`cli/execution_ledger.py:2140-2147`) would block every future lead change in
that run permanently. Any new terminal status that keeps `unknown` rows would
do the same unless the blocker is narrowed.

Gap mismatch **[I]**: `run-supersede-transition`
(`capability-gaps.jsonl:52`) is about the *run lifecycle* having no
"superseded" close, not about attempts. The intake (`intake.md:27`) uses it
for the attempt dead end. The two may need separate treatment.

## 3. Successor creation and lineage

- **[O]** A successor's `predecessors` must equal the ledger's terminal v8
  attempts exactly, in rowid order (`cli/execution_ledger.py:341-342`,
  `:347-363`; ADR 0016:84-87). Any `started` v8 sibling refuses.
- **[O]** Link shape: `{attempt_id, terminal_status, receipt_sha256,
  lead_generation}`. `terminal_status` must be in
  `PREDECESSOR_TERMINAL_STATUSES`. The digest must be hex, or null only for
  `superseded` (`cli/execution_contracts.py:372-389`).
- **[O]** Charter caps count predecessor sends **conservatively**. Paid calls
  count predecessor rows in `started|completed|failed|unknown`, not
  `not_dispatched` (`cli/execution_ledger.py:378-383`). Verifier sends count
  claimed-send or `completed|failed|unknown` (`:1598-1607`). Both feed
  `_v8_action_checks` (`:499-503`). Concurrency and `max_manager_calls` stay
  per attempt (`:492`, `:516`; ADR 0016:93-94), so predecessor `unknown` rows
  do not occupy a successor's concurrency slot.
- **[O]** Expansion headroom is one lineage pool, never refilled by a
  supersede (ADR 0017:79-80). Predecessor consumed grants are inherited
  (`cli/execution_ledger.py:575-579`).
- **[O]** A successor seal checks `lineage_usage` against the ledger count
  (`cli/execution_ledger.py:527-541`).
- **[I]** What a successor needs from an abandoned predecessor: (a) a status
  accepted by `PREDECESSOR_TERMINAL_STATUSES` and `_v8_lineage_locked`, with a
  digest rule (null like `superseded`, or a real sealed receipt digest);
  (b) its `unknown`/`started` rows to keep counting as spent. The current
  paid and verifier queries already do this if the rows keep those statuses,
  or if a new row status is added to the IN lists; (c) no run-wide blocker
  left behind (see the section 2 note); (d) its owner generation bumped, so
  any late writer from the dead process is fenced at the ledger
  (`cli/execution_ledger.py:691-696`, `:303-315`).

## 4. Precedent ADR rules

- **[O]** ADR 0014: "Recovery before dispatch is to … either explicitly
  supersede the claim or abandon the run"
  (`docs/adr/0014-shaper-delivery-ownership.md:28-30`). Ownership is never
  transferred by elapsed time (`:22-23`).
- **[O]** ADR 0016: no terminal `unknown` for v8 (`:13-17`); uncertain calls
  are never resent (`:19-21`); lead change is refused while any row is
  uncertain in any attempt (`:74-78`); `release`/`block` stay unguarded "so
  abandonment remains available" (`:81-82`); manager calls and unobserved
  actions are abandon-only, and "ADR 0012 accepts that a lost response stays
  blocked" (`:118-121`). Rejected: successor-only recovery, because it
  discards spend (`:170-171`).
- **[O]** ADR 0017: supersede/release cancels pending requests and lapses
  grants (`:84-85`); the seal closes open expansions (`:111-112`); a failed
  seal "stays started … and a lead supersede recovers it" (`:112`). That
  remedy does not work when uncertain rows exist (**[I]**).
- **[O]** None of these ADRs defines an attempt-level abandon or cancel
  status, or says how an uncertain send is accounted once abandoned. The
  closest rule is ADR 0016's "stays blocked" for a lost response. Abandonment
  must therefore keep the uncertainty *recorded*, not resolved.

## Implications for requirements

1. A new terminal attempt status is required (for example `abandoned`, plus
   `cancelled` for live cancel per intake decision 3). The existing four
   receipt statuses and `superseded` cannot carry "sealed with uncertainty":
   v8 `unknown` is forbidden by ADR 0016, and `superseded` requires zero
   uncertainty.
2. Uncertain rows must stay *uncertain in the record* (never marked
   completed or not-dispatched without evidence). They must count as spent
   against lineage caps, and they must never be resent (ADR 0012/0016).
3. `lead_change_blocker` and the check in `seal_superseded_attempts`
   (`cli/execution_ledger.py:673`) must stop treating an abandoned attempt's
   rows as live uncertainty, or the work id stays dead for lead changes.
   Scoping the blocker to `started` attempts (or excluding the new terminal
   status) is the narrowest change.
4. `PREDECESSOR_TERMINAL_STATUSES`, `_validate_predecessors` digest rule, and
   `_v8_lineage_locked` must accept the new status. Lineage count queries must
   keep counting its uncertain rows.
5. The abandon act must hold the same fences as supersede: non-blocking
   `recovery_lock` (so a live process refuses `attempt_running`), `run_lock`,
   `send_lock`, `BEGIN IMMEDIATE`, a CAS on owner generation (and ideally the
   event high-water), and a generation bump.
6. Authority: decide whether abandon requires the lead `active`, `released`,
   or either. The released case is the stated fail-closed trap (ADR
   0016:128-130), so it likely must work from `released`. Intake decision 5
   says both operator and Shaper may cancel.
7. Ship a CLI (closes `delivery-lead-claim-cli`). Surface the new status in
   `inspect-delivery`, and fix or define `sealed_receipt.consistent` for
   receipt-less terminal statuses.
8. This needs a new ADR or an amendment to ADR 0016: it changes a stated
   invariant ("uncertain blocks lead change in any attempt").

## Design options for "abandon a stuck attempt"

All options keep: no resend, no evidence-free resolution, recovery_lock
refusal of live runs, owner-generation fencing, lineage caps.

### A. Ledger-only `abandoned` seal (mirror `superseded`)
- Shape: `ExecutionLedger.seal_abandoned(attempt_id, expected_generation,
  expected_event_seq, actor, reason)`. Take the locks, release `allowed`
  grants, close expansions, set `status='abandoned'`, `receipt_path=NULL`,
  bump the generation, and leave `started`/`unknown` rows as they are. The
  blocker and supersede check skip non-`started` attempts. Predecessor digest
  is null (like `superseded`).
- Pros: smallest change; mirrors precedent exactly; no receipt builder
  changes; works without a readable worktree.
- Cons: no durable receipt artifact, so evidence lives only in SQLite
  (sealed_receipt_sha256 is null); the inspect `INCONSISTENT` quirk spreads;
  uncertain rows stay `unknown` forever inside a terminal attempt, which
  every run-wide query must learn to scope.
- Reversibility: high (status value plus scoped queries).

### B. Receipt-backed `abandoned` seal
- Shape: as A, but build and write a receipt with `status: abandoned` (or
  `cancelled`), listing uncertain rows, lineage_usage, expansion and recovery
  blocks. Seal via an extended `finish_attempt` that permits uncertainty only
  for this status. The predecessor link carries a real digest.
- Pros: a durable, verifiable evidence artifact consistent with ADR 0016 R2
  and ADR 0017 "what a receipt proves"; one shape for live cancel (intake
  decision 3 says "receipt is sealed `cancelled`") and stuck abandon; inspect
  consistency works unchanged.
- Cons: touches `validate_receipt` in two places
  (`cli/execution_contracts.py:857`, `:997`), `_build_receipt`,
  `finish_attempt`'s uncertainty invariant, and the predecessor digest rule;
  needs `baseline.json` and the attempt directory readable
  (`cli/delivery_gateway.py:1252`); more tests.
- Reversibility: medium (receipt schema is a durable, validated contract).

### C. Row-level "lost" disposition, then an ordinary seal
- Shape: a new operator disposition (for example `resolved_lost`) marks each
  uncertain row with a terminal row status (`lost`) that counts as spent.
  With nothing uncertain left, the existing `superseded` path (lead change)
  or a `failed` seal works unchanged, and the run-wide blocker clears
  naturally.
- Pros: no run-wide query needs scoping; reuses supersede and successor
  machinery; the operator acts on each row explicitly.
- Cons: conflicts with ADR 0016's "v8 accepts only resolved_completed" and
  ADR 0012's "a lost response stays blocked"; adds a row status to every
  count IN list (`cli/execution_ledger.py:383`, `:489-495`, `:1606`); still
  needs a lead change (or a new seal) to end the attempt; two-step UX.
- Reversibility: medium-low (weakens a stated reconcile invariant).

### D. Lead supersede that allows uncertainty for abandoned attempts
- Shape: add `abandon` to `change_lead_claim`. It seals `started` attempts as
  `abandoned` even with uncertain rows, then bumps the lead generation.
- Pros: one operator act covers "new lead plus successor"; reuses
  `_fence_and_seal_attempts`.
- Cons: couples attempt abandonment to a lead change, although ADR 0016:87-88
  lets a successor run under the same generation; it also cannot serve the
  Shaper-only or released-lead cases cleanly.
- Reversibility: medium.

Tentative lean (for the engineer to decide): **A or B**, with the blocker
scoped to `started` attempts. B is stronger if the live-cancel receipt
(`cancelled`) is in the same slice, because one receipt shape then covers
both cases. A is enough if abandon may stay ledger-only like `superseded`.
