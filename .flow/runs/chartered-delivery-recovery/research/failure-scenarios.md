# Research note: chartered delivery failure states and recovery boundaries

**Question:** What failure states can a chartered v8 delivery attempt end in
today, what does the operator see and can do for each, and what recovery
workflow and acceptance criteria does each state need?

**Evidence status legend:** [O] observed in code, [I] inferred, [A] assumed.

## Actors

- **Engineer**: runs `flow run` CLI commands, reads ledger/receipt state,
  decides whether to resume, reconcile, or abandon an attempt. [A]
- **Delivery Lead successor/operator**: the identity that takes `resume` or
  `supersede` action on a fenced lead claim (`change_lead_claim`,
  `cli/delivery_control.py:210`). [O]
- **Shaper**: not a runtime actor for recovery today; referenced only as the
  future consumer of resumability for delegated-expansion approval (brief,
  adoption step 5). [A] — out of scope for this increment per brief.

## Boundaries

### 1. Manager call started or `unknown`
- Ledger: `attempts.status='started'`; a manager call row is `started` (send
  claimed, no response) or `unknown` (crash after send, before response) —
  `ExecutionLedger.decide_manager_call` (`cli/execution_ledger.py:496`),
  `mark_manager_unknown` (`:598`), `observe_manager_response` (`:574`).
  `_claim_recovery_locked` (`:250`) fences `started`→`unknown` on any new
  recovery claim and bumps `owner_generation`.
- Operator options today: for v6/v7/v8, `resume_delivery` and
  `recover_delivery` (`cli/delivery_gateway.py:567`, `:658`) both hard-require
  `execution_protocol_version == 5` (lines 584, 675) and raise
  `ContractError`. `flow run inspect-delivery` (`cli/delivery_projection.py:56`)
  can show the state but performs no mutation. There is no chartered-path
  reconciliation command.
- Desired: reconcile then resume — evidence-backed resolution of the
  `unknown` call (never resend), then continue the same attempt under a new
  fenced generation, mirroring `resolve_unknown` (`:889`) for manager calls.
- Acceptance criterion (candidate): given a chartered attempt with a manager
  call in `unknown`, `flow run recover-delivery-lead` (or its v8 successor)
  resolves it from durable evidence only, never re-sends the manager call, and
  resumes the attempt under `owner_generation+1`.
- **Implication for requirements**: manager-call reconciliation must be
  extended to protocol 6/7/8, reusing the `resolve_unknown` evidence pattern
  rather than inventing a second recovery path.

### 2. Producer grant issued but not consumed
- Ledger: `actions.status='allowed'`, `grant_id` set, no `worker_dispatched`
  event. `consume_grant` (`:609`) enforces a 60s grant expiry against the
  `policy_allowed` event; on timeout it flips to `denied/grant_expired`.
  `close_pre_send_failure` (`:669`) exists for the pre-send-crash case and
  checks no `worker_dispatched`/`adapter_send_started` event exists.
- Operator options: none chartered-specific; `close_pre_send_failure` is
  already generation-fenced and protocol-agnostic (checks protocol in
  `{3,4,5,6,8}` — note 7 is absent, line 684). No CLI entry point calls it for
  an operator; it's only reached inline in `on_action`/`prepare_verifier_send`
  exception handlers (`:909-912`, `:926-930`).
- Desired: resume — an unconsumed grant is safe to expire and re-grant; no
  provider was ever contacted. Terminal only if the grant expiry policy alone
  cannot restore forward progress (e.g., attempt otherwise closed).
- Acceptance criterion: an attempt with an `allowed`, unconsumed, expired
  grant becomes eligible for a fresh grant on resume without any
  reconciliation step, and this holds for protocol 7 as well as 6/8.
- **Implication**: the v7 gap in `close_pre_send_failure`'s protocol allow-list
  (line 684, missing `7`) is a defined-scope defect the recovery work must fix
  or explicitly except.

### 3. Producer send claimed but no response
- Ledger: `actions.status='started'` with `worker_dispatched` and
  `adapter_send_started` events recorded but no `response_observations` row.
  This is the "uncertain provider outcome" case the brief calls out
  ("Never resend a provider call whose outcome is uncertain"). `mark_unknown`
  (`:879`) is the transition triggered from the `except` block at
  `delivery_gateway.py:953-956`.
- Operator options: chartered path has no equivalent to v5's
  `recover_delivery`, which replays a durable Claude CLI event trace
  (`_stream_result`, event_path digest check, `:693-707`) to reconstruct the
  result without resending. v6/7/8 producers (claude/codex/ollama workers)
  have no such durable trace-replay path defined yet for reconciliation.
- Desired: reconcile then resume — require provider-specific durable evidence
  (e.g., a recorded event/trace file with a matching digest) before treating
  the action as resolved; otherwise stay `unknown` and terminal-pending-
  operator-input.
- Acceptance criterion: for each chartered producer provider, recovery either
  (a) locates durable send evidence proving the outcome and resolves without
  resending, or (b) refuses resume and reports the action as requiring
  operator evidence — it never resends.
- **Implication**: this boundary is evidence-scope-defining. Requirements
  must enumerate, per producer provider (claude/codex/ollama), what durable
  evidence exists today to prove send outcome; where none exists, that is an
  explicit non-goal or a new evidence requirement, not a silent resend.

### 4. Producer completed but edit/test verification incomplete
- Ledger: `actions.status='completed'` for the producer action (set at
  `delivery_gateway.py:942` before edit/test verification runs at `:947-950`).
  If `_verify_chartered_edit` or `_run_chartered_test` then raises, the
  exception is caught by the outer `except` at `:953`, but
  `response_completed=True` already, so `mark_unknown` is *not* called
  (`:954` guards on `not response_completed`). The action stays `completed`
  while `edit_evidence`/`test_evidence` are unset for this run.
- Operator options: re-running `_execute_prepared_delivery` (via resume) would
  recompute `initial_snapshot` (`:778-784`) and re-verify edit/test from the
  worktree state each time — this is idempotent verification, not send
  replay, so it is safe to simply resume and let it re-check.
- Desired: resume — no reconciliation needed since verification is a local,
  repeatable check, not a provider call.
- Acceptance criterion: an attempt whose producer action is `completed` but
  whose edit or test verification failed resumes cleanly and re-verifies from
  the pinned baseline/diff without any new provider send.
- **Implication**: recovery for chartered attempts should distinguish
  "verification-incomplete" from "provider-uncertain" — the former needs no
  operator evidence at all, only a resume path that currently doesn't exist
  for protocol 6/7/8.

### 5. Verifier input bound or send claimed but no response (v8 only)
- Ledger: `verifier_inputs` row exists (`prepare_verifier_send`, `:626`), with
  `send_claimed_at` set (event `verifier_send_claimed`, `:662`), but no
  `verifier_evaluations` row and no `response_observations` row. Action status
  is `started`. On send failure the `except` at `:953-956` marks the action
  `unknown` (since `response_completed` is false pre-response).
- Operator options: none. `resume_delivery`/`recover_delivery` reject non-v5.
  There is no path to replay a verifier send from durable evidence.
- Desired: reconcile then resume — same evidence-backed-only rule as
  boundary 3, but scoped to the verifier's own durable trace/evidence and
  bound `input_digest`/`diff_digest`/`test_digest` (must match current
  evidence, per the stale-evidence gate at `:999-1004`).
- Acceptance criterion: recovery for a claimed-but-unanswered verifier send
  either resolves from durable evidence matching the bound digests, or leaves
  the action `unknown` and reports it; it never re-sends, and it never accepts
  evidence bound to a diff/test digest that no longer matches current
  `edit_evidence`/`test_evidence`.
- **Implication**: this is the most novel case — v5 has no verifier concept.
  New durable-evidence and digest-matching rules are required specifically
  for verifier reconciliation.

### 6. Verifier completed but not yet evaluated
- Ledger: `actions.status='completed'` (set at `:942`), `response_observations`
  row exists, but no `verifier_evaluations` row — a crash between `:942` and
  `evaluate_verifier` at `:945`. The replay branch explicitly anticipates this:
  "A crash can land between completion and evaluation. Replay re-evaluates
  the stored response; it never resends" (`:866-878`).
- Operator options: this is the one boundary the current on_action replay
  branch already self-heals, but only inside a live `_execute_prepared_delivery`
  call triggered by the underlying MAF supervisor's own replay/dedup of the
  same `action_id` — not through any operator-facing resume for a *closed or
  crashed* attempt, since chartered resume itself doesn't exist. `flow run
  inspect-delivery` shows `verifier_evaluations`/`verifier_usage` for
  visibility only (`delivery_projection.py:50-52`).
- Desired: resume — this case needs no new evidence-gathering, only a way to
  re-enter `_execute_prepared_delivery` for a closed/crashed attempt so the
  existing replay-evaluate logic (`:866-878`) can run.
- Acceptance criterion: resuming an attempt with a completed-but-unevaluated
  verifier action re-evaluates deterministically from the stored response and
  bound digests, producing the same evaluation as if no crash occurred, with
  zero new provider sends.
- **Implication**: the missing piece here is purely "allow chartered resume
  to re-enter the gateway loop," not new evidence logic — this narrows the
  required work for this specific state.

### 7. After a verifier evaluation (retry-eligible or not)
- Ledger: `verifier_evaluations` row exists; `verifier_usage`
  (`:822`, `_verifier_usage` `:805`) computes `retry_eligible` from the latest
  outcome (`valid_fail`/`unusable`) and remaining `max_verifier_calls`
  headroom.
- Operator options: `flow run inspect-delivery` surfaces `verifier_usage` and
  `verifier_evaluations` for read-only inspection. No resume path exists to
  act on `retry_eligible=True` for a crashed/closed attempt — only a live
  in-progress MAF loop can request another verifier call under the manager's
  own logic.
- Desired: resume (retry-eligible) — continue the attempt and let the
  manager decide whether to spend the retry; terminal (not retry-eligible,
  i.e., cap reached or a `valid_pass`/non-retryable outcome) — attempt should
  finish and seal a receipt, not hang open.
- Acceptance criterion: resuming a closed/crashed attempt whose last
  evaluation is retry-eligible allows exactly one more verifier grant up to
  `max_verifier_calls`; resuming one that is not retry-eligible instead drives
  straight to receipt sealing with the existing terminal evaluation.
- **Implication**: retry-eligibility is already computed correctly; the gap is
  only that resume cannot reach this decision point for chartered attempts.

### 8. Receipt sealing
- Ledger: `finish_attempt` (`:1235`) writes `receipt.json` and sets terminal
  status inside `ledger.send_lock()` with `assert_owner` (`delivery_gateway.py
  :1051-1059`). A crash between computing `receipt` and this transaction
  leaves `attempts.status='started'` with no `receipt_path`, i.e.
  indistinguishable from boundary 1/7 without a receipt file — but nothing
  provider-side is uncertain; only Flow-local sealing was interrupted.
- Operator options: none for chartered attempts. For v5, resume re-derives the
  same receipt fields deterministically from the ledger snapshot, so a crash
  here is naturally idempotent on retry (no side effect to redo).
- Desired: resume — this is a pure local determinism concern; recompute the
  receipt from the ledger snapshot and re-attempt the atomic write/transition.
- Acceptance criterion: re-running the terminal-receipt path after a crash
  between receipt-computation and `finish_attempt` produces a byte-identical
  receipt and succeeds idempotently, with no new provider or ledger side
  effects beyond the completed write.
- **Implication**: needs no new evidence machinery, only that resume can reach
  this final step for protocols 6/7/8, and a test proving idempotent receipt
  content across a simulated crash-and-retry.

### 9. Fenced or superseded lead claim
- Ledger/state: `run.json` `delivery.owner_status` in
  `{attention_required, released}` after `change_lead_claim` (`:210`); the
  envelope's `delivery_lead_claim.generation` becomes stale, so
  `delivery_authority_guard` (`:40-55`) raises `DeliveryControlError` on any
  further dispatch/ledger mutation under the old generation.
  `change_lead_claim` also refuses `resume`/`supersede` while
  `current.get("pending_unknown_actions")` is truthy (`:239-240`) — i.e., an
  operator cannot advance lead ownership past an unresolved `unknown` state.
- Operator options: `flow run` has no listed subcommand wrapping
  `change_lead_claim` directly in the grepped CLI surface (only
  `resume-delivery-lead`, `recover-delivery-lead`, `inspect-delivery`,
  `resume-execution`, `resolve-execution`, `continue-resolved-execution` were
  found at `cli/flow.py:574-621`); `change_lead_claim` appears to be invoked
  from elsewhere (delegated-expansion or operator-controls work, per brief
  scope note) — this needs confirming, not assuming. [I, needs confirmation]
- Desired: terminal for the fenced generation (never resumable under the old
  claim — ADR 0014: elapsed time never transfers ownership) but the run itself
  is reconcile-then-resume under the *new* generation once a successor claim
  is `active` and any blocking `unknown` action is resolved first.
- Acceptance criterion: an attempt whose envelope generation no longer matches
  `run.json`'s active claim fails closed (raises, no mutation) under the old
  generation; after an explicit `resume`/`supersede` claim change (which
  itself is refused while any action is `unknown`), a fresh chartered attempt
  or resumed attempt can proceed under the new generation.
- **Implication**: lead-claim fencing already composes correctly with the
  "resolve unknown before ownership can move" rule; the requirements need to
  state explicitly that unknown-resolution is a *precondition* for
  lead-claim resume/supersede, not a parallel path.

## Open questions
- Which CLI surface actually invokes `change_lead_claim` today, and is it
  in this increment's scope? [needs confirmation — grep of `cli/flow.py`
  found no direct subcommand]
- What durable evidence exists per producer/verifier provider (claude, codex,
  ollama) to reconstruct a send outcome without resending? This is unresolved
  and should stay explicitly undefined until each provider's trace mechanism
  is inventoried (see boundary 3).
