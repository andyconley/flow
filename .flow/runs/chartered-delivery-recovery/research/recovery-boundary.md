# Research: chartered recovery boundary (v6/v7/v8)

- Role: solution-architect (opener). Date: 2026-09-23.
- Code read: `/Users/andyconley/.codex/worktrees/verifier-contract/flow` (v8 branch). G = gateway `cli/delivery_gateway.py`, L = `cli/execution_ledger.py`.
- Status key: **O** = observed in code, **I** = inferred.

## 1. Boundary map

| Mechanism | Verdict | Evidence | Implication for requirements |
|---|---|---|---|
| `resume_delivery` gate | Blocked | G:584 requires v5. G:607-619 rebuilds a missing reply with v5 `_verify_edit` and `_run_targeted_test`, keyed on `provider == "claude"` (O). | You need a chartered resume entry point that rebuilds the reply from producer and verifier instance IDs. It must never call the v5 fixtures. |
| `recover_delivery` | Blocked | G:675 requires v5. G:686 selects by `assignment_id == "claude-implementer"`. G:674/693 read the Claude event trace only (O). A Codex editor has no equivalent trace path (I). | Requirements must say what evidence resolves an unknown chartered producer or verifier for each provider. |
| Interruption marker | Blocked | G:986 applies `not chartered`. A chartered transport failure with no uncertain sends therefore finishes `failed` (G:1005, 1059) (O). | Decide whether chartered attempts get `interrupted` with `started` kept, or a failed-then-continued shape. |
| `_execute_prepared_delivery` re-verification | Needs an adaptation | G:778-782 re-runs `verify_edit` and `test_runner` whenever a producer is completed (O). The chartered diff check is deterministic, because the recorded `repair.diff` must match byte for byte (G:543-545) (O). The test re-run produces a new `output_sha256` (G:561-564), because output includes timing (archive note). | Edit evidence can be re-verified. Test evidence must be reused from its durable record, not re-captured. That record does not exist yet (I). |
| Stale-evidence gate | Blocked for v8 resume | G:999-1004 compares the evaluation's `test_evidence_digest` with the re-captured test digest (O). A resumed v8 pass therefore always fails (I, high confidence). | Pin down the source of truth: the verifier input's `test_digest` (L:656), or a new durable test-evidence record. |
| Owner fencing (`claim_recovery`, `_assert_owner`) | Reusable as-is | L:250-276 bumps the generation and converts `started` to `unknown`. L:212-224 applies to all v2+ recovery rows (O). For v7/v8, `create_attempt` seeds the ledger generation from the lead-claim generation (L:240-243) (O). | Requirements must keep two counters distinct: the attempt fence (ledger) and the lead authority (`run.json`). |
| `delivery_authority_guard` and lead claim | Blocked after a lead successor | The guard compares `run.json` with the envelope's embedded claim (`delivery_control.py:49-54`). The envelope is immutable (G:590; L:318). `change_lead_claim` resume or supersede sets generation+1 (`delivery_control.py:255`). An `attention` status also fails the guard (`:50`) (O). After an ADR 0014 resume, the old attempt can never pass the guard (I). | Pin down how a successor lead adopts an existing attempt: a new attempt, or a linked lead-adoption record. The envelope must not be mutated. |
| Unknown-blocks-successor check | Inert | `delivery_control.py:239` reads `pending_unknown_actions`, but no code writes it (O, grep). | Ledger `unknown` state must reach lead-change decisions. |
| `resolve_unknown` | Reusable as-is | L:889-948 is protocol-agnostic and validates the v8 verifier shape (L:924-930) (O). | Resolution can serve all chartered versions. Only the evidence that feeds it is new. |
| Grant expiry | Blocked | The 60 s TTL applies at L:618, L:646 (v8 verifier) and L:566 (O). A replayed `allowed` decision (L:328) with an expired grant is denied, then G:908 raises (O). `regrant_not_dispatched` uses v2 work-wide caps of 6/3 (L:962-964) (O). `close_pre_send_failure` omits v7 (L:684) (O, likely a defect). | A proven-unsent chartered action needs a regrant under chartered caps (delegation, paid, verifier). Fix the v7 omission. |
| Continuation epochs | Blocked | `start_magentic_continuation` (L:1421), `finish_magentic_continuation` (L:1268) and `retry_failed…` (L:1375) are v5-only. For non-v5, `begin_continuation` looks up the v2 `pending_delegate` sequence-3 link (L:1329). `decide` accepts `unknown` attempts only for v5 (L:319) (O). | Either widen the v5 Magentic epoch to 6-8 or define a chartered epoch. The v2 branch must not be reused. |
| Checkpoint bind/read and MAF restore | Reusable as-is | L:1103 and L:1146 accept v5-8 with workflow `flow-magentic-delivery-v{n}`. The supervisor accepts resume for v5-8 (`maf_supervisor.py:450,467`). The runner validates `provider_choice` for v7/v8 (`runtime/maf_runner/delivery_lead.py:286-287`) (O). | No runtime work is needed. The requirements scope is the gateway and ledger. |
| Verifier inputs, evaluations, cap | Reusable as-is | Replay re-evaluates and never resends (G:866-879). Evaluation is idempotent (L:794-798). Cap counting keeps `unknown` reserved (L:393, 810) (O). | Resume must not re-prepare an input whose send was already claimed (L:652). Recovered unknown verifier sends consume allowance, per ADR 0015. |
| Receipt and linked receipt | Needs an adaptation | Continuation evidence is protocol-agnostic (`execution_contracts.py:740-748`), and the linked path is written at G:1049 (O). Delivery receipts must equal the envelope's `delivery_lead_claim` (`execution_contracts.py:714-717`) (O). | A linked receipt cannot yet record a successor lead generation. The requirements must name that field or forbid successor adoption. |

## 2. Capability decisions the requirements must pin down

1. **Recovery shape.** Choose between two shapes:
   - Same-attempt resume (`started`, fenced by `claim_recovery`) for a clean crash or transport loss.
   - A continuation epoch plus a linked receipt only after a terminal `unknown` or `failed` attempt.

   The v5 precedent uses both. Mirror it rather than inventing a third.
2. **Evidence reuse.** Decide which durable record is authoritative on resume: the targeted test's `output_sha256`, the diff digest, and the file digests. Choose one:
   - a new ledger test-evidence row written before the verifier send;
   - the `verifier_inputs.test_digest`, which does not exist for v6/v7.

   Then decide whether resume may re-run the test at all. A deterministic diff re-check is safe.
3. **Lead-successor interaction.** Choose one:
   - (a) A superseded or resumed lead forbids resuming the old attempt. The operator starts a new attempt.
   - (b) A linked adoption record binds the new claim digest to the old attempt, and the guard and receipt accept it.

   ADR 0014 requires either choice to be explicit and never time-based.
4. **Unknown-to-lead propagation.** Decide whether ledger `unknown` must block `change_lead_claim` resume or supersede. Today it does not.
5. **Unsent-grant recovery.** Decide whether an expired or unconsumed chartered grant can be regranted under the chartered caps, and whether that regrant counts against `max_delegations` and `max_paid_worker_calls` again.
6. **Per-provider unknown evidence.** Decide what positive evidence resolves an unknown Codex or Claude producer and an unknown v8 verifier.
7. **Version scope.** Choose one:
   - v8-only recovery, with v6 and v7 staying inspection-only;
   - v7 and v8, with v6 inspection-only.

   ADR 0014 already says v6 is "not executable or resumable through this path". v7 has no verifier bindings, so decision 2 needs a separate answer for it. Recommend v8 only unless v7 has live stuck attempts.

## 3. Constraints by section

- **ADR 0012, Decision:** the ledger is read before any MAF restore. A checkpoint "cannot grant or infer permission to call a provider". A dispatch-start record without a durable response blocks automatic continuation. Operator resolution is append-only. The implication is that recovery sequencing must reconcile the ledger first.
- **ADR 0012, Consequences:** conservative blocking is acceptable. A lost response may remain blocked.
- **ADR 0014, Compatibility and recovery:** v6 is not resumable. A stale generation is fenced at every dispatch boundary. Recovery requires explicit resume or supersede. Elapsed time "cannot transfer ownership", so grant expiry must never trigger an implicit successor.
- **ADR 0015, Recovery:** observations, inputs, and evaluations are distinct records, and exact evaluation replay is idempotent. Changed bindings are rejected, which is why test evidence must be reused. Unknown sends consume the verifier allowance unless positive no-dispatch evidence exists.
- **ADR 0015, Consequences:** v7 receipt meaning is unchanged, so any v7 recovery must not change v7 receipt validation.
- **`scaffolds/default/standards/architecture.md`, ADR convention:** this changes data ownership (the lead-adoption or evidence record), so it needs a new ADR or an ADR 0014/0012 amendment.
- **`architecture.md`, Domain rules and Core principles:** keep recovery eligibility deterministic and testable apart from MAF. "prefer reversible decisions": a new epoch is additive, whereas mutating an envelope is irreversible.
