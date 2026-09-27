# Research: what "the Shaper" is, and how Shaper authority vs operator authority is modelled

Question: what is "the Shaper" today, and how is its authority recorded/enforced, so a
Shaper-initiated cancel can reuse the same model?

## 1. Who/what "the Shaper" is

- **Observed.** The target-boundary diagram: `U[Andy] --> S[Shaper: charter and bounded
  approvals] --> F[Flow: lifecycle, policy, system of record]`. Andy sits upstream of the
  Shaper; the Shaper sits upstream of Flow. `docs/maf-adoption-design.md:42`.
- **Observed.** `shaper_gateway.submit_charter` (exercised by
  `tests/test_shaper_gateway.py:8,20-31`) is an external submission path (the MCP ingress
  mentioned at `docs/maf-adoption-design.md:28,62,85`) that proposes a charter into
  `defining` state — `execution_started: False`, no `approve-definition` gate — and cannot
  itself approve or execute. So a "Shaper" in this code is an external caller/session (a
  ChatGPT- or Claude-side agent, reached over MCP) that can *propose*, not *decide*.
- **Observed.** The actual authority object is not a person or session at all: it is the
  sealed **Shaper Contract** (`cli/delivery_contracts.py:226-236`, `SHAPER_CONTRACT_VERSION
  = 3` at `cli/delivery_contracts.py:17`), built from a reviewed `shaper_intent.json`
  artifact (`cli/delivery_contracts.py:142-201`, fixture at
  `tests/shaper_intent_fixture.py:4-54`). ADR 0014 states the model directly: "Flow seals a
  runtime-neutral Shaper Contract and derived Delivery Charter when `start-plan`
  succeeds" (`docs/adr/0014-shaper-delivery-ownership.md:8-9`), and "MAF may coordinate a
  chartered roster, but it cannot create authority, substitute a provider, amend the
  charter, or accept work" (`docs/adr/0014-shaper-delivery-ownership.md:13-15`).
- **Observed.** Even the *approver* recorded on the sealed Delivery Charter is literally the
  engineer, not a distinct "Shaper" identity: `"approver": {"identity": "engineer", "event":
  shaper["approval_event"]}` (`cli/delivery_contracts.py:268`). Nothing in the sealed record
  names a Shaper actor/session id; "Shaper" is a role label for whoever authored/approved the
  intent before `start-plan`, and its only durable trace is the contract content itself
  (`approval_history` entries such as `{"event": "approve-definition", "authority":
  "engineer"}` in `tests/shaper_intent_fixture.py:46`).
- **Inferred.** "The Shaper" is therefore best read as *a role, expressed entirely through a
  sealed artifact* (the Shaper Contract / Delivery Charter), not as an authenticated actor
  Flow can check at decision time. Confirmation would be an ADR or design note stating this
  explicitly; none found. The closest explicit statement is ADR 0014's "runtime-neutral
  Shaper Contract... Providers and MAF receive a later projection and cannot add fields to
  these sealed artifacts" (`cli/delivery_contracts.py:1-5`), which frames the Shaper as the
  authorizing document, not a runtime party.

## 2. What the charter delegates to "the Shaper," and how it is exercised later

- **Observed.** `approval_matrix.charter_amendment: "shaper_or_engineer"` is a real field in
  the intent/contract (`tests/shaper_intent_fixture.py:37`), sealed and validated by
  `validate_shaper_intent` (`cli/delivery_contracts.py:171-172` enforces
  `provider_dispatch == "Flow_grant"`; the amendment field itself passes through
  unvalidated content-wise, i.e. Flow does not currently enforce *who* satisfies
  `shaper_or_engineer` beyond documentation — inferred from absence of any check on that
  string elsewhere in `delivery_contracts.py`).
- **Observed.** The one delegation that *is* mechanically enforced is expansion headroom
  (ADR 0017, `docs/adr/0017-delegated-expansion-headroom.md:17-23,32-41`). The Shaper's only
  concrete, code-checked delegated power is: at definition time, seal
  `expansion_headroom` into the intent (`cli/delivery_contracts.py:104-121,194-196`), which
  the Delivery Charter carries at `limits.expansion_headroom`
  (`cli/delivery_contracts.py:263`).
- **Observed.** At runtime, a limit hit *within that sealed headroom* is granted
  automatically, attributed to `authority="charter_headroom"`, with no actor/identity
  check at all — `cli/execution_ledger.py:430,467,470,577`. This is the one place code
  actually distinguishes "Shaper-authorized" (pre-sealed, self-executing, no CLI actor) from
  "engineer-authorized" (see below).
- **Observed.** Anything beyond sealed headroom escalates and pauses the attempt; only
  `flow run decide-expansion` can resolve it, and every such grant is attributed to
  `"engineer"` literally in the ledger row: `db.execute(... (grant_id, request_id, ...,
  "engineer", decision, ...))` — `cli/execution_ledger.py:793-796`. There is no
  `"shaper"` value ever written to `expansion_grants.authority`; the only two authorities
  the schema distinguishes are `charter_headroom` (pre-sealed, automatic) and `engineer`
  (explicit, CLI-driven, one unit at a time) — ADR 0017 confirms: "A grant is authorised in
  one of two ways: by headroom the Shaper sealed into the charter, or by an explicit
  engineer decision" (`docs/adr/0017-delegated-expansion-headroom.md:20-22`).

## 3. `flow run decide-expansion`: `--actor`, auth, and Shaper/Andy distinction

- **Observed.** CLI surface: `run_decide_expansion.add_argument("--actor", required=True,
  help="declared decider, recorded as attribution")` (`cli/flow.py:598`); also
  `--expected-generation` (int, required, "ledger owner generation shown by
  inspect-delivery," `cli/flow.py:596-597`) and `--explanation` (required,
  `cli/flow.py:599`).
- **Observed.** Enforcement in `ExecutionLedger.decide_expansion`
  (`cli/execution_ledger.py:746-802`): `actor` and `explanation` are validated only as
  non-empty strings ≤256/2048 chars (`cli/execution_ledger.py:756-758`) — **no
  authentication, no allowlist of actor values, no check that `actor` is "Andy" vs
  "Shaper" vs anything else.** `--actor` is free-text attribution, not an authorization
  gate. Authorization instead comes from *possessing the CLI/filesystem access* and
  supplying the correct `expected_generation` (compare-and-swap against
  `owner_generation`, `cli/execution_ledger.py:767-768`) and hitting a truly-paused attempt
  (`cli/execution_ledger.py:763-776`).
  So today's actual authority model for `decide-expansion` is: whoever can run the CLI
  against the run directory can decide, and the `actor` string is purely a label recorded
  for audit (event `expansion_decided` with `"actor": actor.strip()`,
  `cli/execution_ledger.py:798-799`, and in the grant row,
  `cli/execution_ledger.py:793-796`).
- **Observed.** The written decision is always attributed `"engineer"` in the grant row
  regardless of the `--actor` string passed (`cli/execution_ledger.py:794`) — the *free-text*
  `--actor` value is stored for the event log, but the `expansion_grants.authority` column
  is hardcoded to `"engineer"` for any explicit decision, never to the `--actor` value
  itself and never to `"shaper"`. So even a Shaper-labelled `--actor` on `decide-expansion`
  is ledgered under `engineer` authority, not a separate Shaper authority.
- **Inferred.** ADR 0017's design intent — "Route proposed expansion to delegated Shaper
  approval or Andy according to the charter" (`docs/maf-adoption-design.md:85`, step 5
  acceptance) — is only half-built: the "delegated Shaper approval" half is the *automatic*
  `charter_headroom` path (no `decide-expansion` call at all); "Andy" is the explicit
  `decide-expansion` path. There is no third, distinct "Shaper calls decide-expansion"
  code path today.

## 4. Delivery Lead claim `owner` / `owner_actor` fields (`cli/delivery_control.py`,
   `cli/execution_ledger.py`)

- **Observed.** The Delivery Lead claim (a lifecycle-level record, distinct from the
  execution-ledger's `owner_actor`) has an `owner` field. At `start-plan` it is hardcoded:
  `"owner": "delivery-lead"` (`cli/delivery_control.py:167`) — not "Shaper" or "Andy", a
  fixed role string for generation 1.
- **Observed.** `change_lead_claim(action, ..., owner=...)` in
  `cli/delivery_control.py:210-267`: for `resume`/`supersede` the caller must pass a
  non-empty free-text `owner` string (`cli/delivery_control.py:251-252`,
  `"resume or supersede requires an explicit owner identity"`); for `attention`/`release`
  the previous claim's `owner` is carried forward unchanged
  (`cli/delivery_control.py:332`, `json.loads(previous_claim.read_text())["owner"]`). No
  format or identity check on `owner` beyond non-empty-string — again free-text attribution,
  not an authenticated identity.
- **Observed.** Separately, the SQLite execution ledger has its own `owner_actor` column
  (`cli/execution_ledger.py:79,146,206`), set to `"initial"` at attempt creation
  (`cli/execution_ledger.py:333`), to `"superseded"` on lead-change supersede
  (`cli/execution_ledger.py:695`), and to an explicit `actor` string on
  `claim_recovery`/`claim_chartered_recovery` (`cli/execution_ledger.py:814,824,847,873`) —
  same pattern as `decide_expansion`: `actor` is a required, length-bounded, non-empty
  string, validated for shape only, never for identity (`cli/execution_ledger.py:814-815,
  847`).
- **Observed.** No code anywhere in `delivery_control.py` or `execution_ledger.py`
  distinguishes an `owner`/`owner_actor` value of "Shaper" from "Andy" or any other string;
  the whole authority model for *who may act* is: CLI/filesystem access + correct
  `expected_generation` + a non-empty attribution string. Identity is asserted, not
  verified, everywhere in this codebase (consistent with the single-user context noted in
  `MEMORY.md`: Andy is Flow's only user).

## Implications for requirements

Given the above, "the Shaper" has no separate authenticated identity or runtime session
Flow can check today. Its authority is entirely pre-sealed (definition-time contract
content) plus free-text attribution at decision time. Concretely, "Shaper may cancel"
could mean one of:

- **Option A — same free-text attribution model as `decide-expansion`/`change_lead_claim`.**
  A cancel command takes `--actor` (any non-empty string, ≤256 chars) purely for
  attribution, exactly like `decide-expansion` and `claim_recovery`/`claim_chartered_recovery`
  today. No distinction is enforced between "Shaper" and "Andy" as callers — whoever can run
  the CLI can cancel. This is the cheapest option and matches every existing actor field in
  the codebase (`owner`, `owner_actor`, `decide_expansion.actor`) precisely: none of them
  gate on identity, all of them just record it.
- **Option B — mirror the `charter_headroom` automatic-authority split.** Define a sealed,
  charter-level "cancel authority" analogous to `expansion_headroom`: e.g., the Shaper
  Contract could pre-seal conditions (a runtime/cost bound, a limit) under which cancel
  fires automatically, attributed to `charter_headroom`-style authority with no CLI actor
  at all, while anything outside that pre-sealed condition requires an explicit
  engineer-attributed `decide`-style call. **No such automatic-cancel trigger exists in code
  today** — checked `runner_limits.py`-sourced ceilings and `EXPANSION_CEILINGS`
  (`cli/delivery_contracts.py:40-46`) and found no cancellation-shaped bound (e.g. no sealed
  wall-clock/cost ceiling that fires a cancel); the only automatic charter-driven event
  found is expansion grants. Building this option is new design work, not reuse.
- **Recommendation:** Option A. It reuses the existing, already-consistent pattern
  (`--actor` as attribution, not authorization) used by `decide-expansion`,
  `change_lead_claim`, and `claim_recovery`/`claim_chartered_recovery`. It requires no new
  authority concept, and it matches the fact that no code path today treats "Shaper" as a
  distinct, checkable identity. Recording `--actor` with a value like `"shaper"` or the
  Shaper Contract id gives an audit trail without inventing enforcement machinery the rest
  of the codebase doesn't have.

**Open question for the engineer:** should a Shaper-initiated cancel be gated on anything
beyond free-text attribution (e.g., must reference the sealed Shaper Contract id / charter
digest to prove it originates from the same charter that's being cancelled), or is
matching the existing `--actor`-as-attribution pattern (Option A) sufficient — i.e., is
"the Shaper may cancel" a statement about *who is allowed to invoke the cancel command in
practice* rather than something Flow needs to verify?
