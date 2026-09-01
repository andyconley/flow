# Orchestration Safety

Use this standard whenever work is delegated, concurrent, high-risk, or mutates shared state. It defines the contract between Flow lanes; it does not add a lane or launch agents.

## Required artifact

Revision-2 runs keep the machine contract at:

```text
.flow/runs/<work-id>/orchestration.json
```

The manifest uses `schema_version: 1` and contains `work_id`, `mode`, `risk`, `assignments`, `shared_state`, `reconciliation`, and `verification`. Unknown additive object fields are allowed. Unknown controlled values, wrong types, unsafe paths, and omitted required fields fail closed.

Run the structural checks at the moment they matter:

```bash
flow run validate-orchestration <work-id> --stage dispatch
flow run validate-orchestration <work-id> --stage handback
flow run validate-orchestration <work-id> --stage acceptance
```

Stages are cumulative. Run `dispatch` immediately before launching a provider or mutating shared state; lifecycle gates are the backstop. The CLI validates declarations and referenced-artifact existence. It cannot inspect hidden runtime grants, establish semantic truth, or prove that a provider actually followed its brief.

## Agent briefs and assignments

Every assignment records:

- a stable id, lane, role, and provider identity
- a readable brief and input-evidence inventory
- read scopes and either exact write scopes or explicit read-only status
- every required capability with `confirmed`, `missing`, or `unknown` status
- output path and format, observable success criteria, expected claim statuses
- `concurrent` or `serialized` coordination with a stable group

Only `confirmed` satisfies a required capability. `unknown` is honest uncertainty, not proof. Repository paths are relative to the repository root, may not escape through traversal or symlinks, and use ancestor/descendant semantics for overlap. Writable concurrent assignments must have disjoint scopes; overlapping assignments share one serialized group. A read-only assignment may write only its declared report under the containing run.

External regions are compared only within the same exact target identity. That comparison is declaration-level; aliases or semantically overlapping coordinates still require human review.

## Claim provenance and reconciliation

Material claims influence scope, safety, a contract, validation, a disposition, or a release assertion. Classify them as:

- `observed` — directly supported by cited evidence
- `inferred` — linked to supporting observations
- `recommended` — a proposed choice with a recorded decision owner
- `unverified` — plausible but not checked

Every material conflict or claim receives `accepted`, `rejected`, or `deferred` disposition in the reconciliation record. An unverified claim cannot be accepted as durable fact. Unresolved reconciliation blocks handback and acceptance.

## Calculated risk

Risk is calculated from controlled values, never selected by free text.

Any hard trigger makes the work high-risk:

- `destructive_or_irreversible`
- `production_or_shared_external_mutation`
- `security_or_privacy_boundary`
- `loss_bearing_data_migration`
- `regulated_personnel_safety_or_customer_access`

Without a hard trigger, two or more aggravating factors make the work high-risk; zero or one is standard-risk:

- `large_blast_radius`
- `weak_rollback`
- `weak_or_delayed_observability`
- `concurrency_or_cross_system_coordination`
- `material_unresolved_ambiguity`
- `author_only_validation`
- `unverified_claim_for_durable_truth`

Verification roles reference stable assignment ids: `producer_assignments`, `evidence_collector_assignment`, and `verifier_assignment`. The validator derives provider identity from those assignments, and every mutable shared-target owner must appear in the producer list. High-risk acceptance requires a verifier assignment and stable provider identity distinct from every producer and from the evidence collector whose evidence is being certified. Standard-risk work records the same roles but does not require separation.

## Shared and external mutations

Every shared target records its exact identity, mutation type (`additive`, `structural`, `destructive`, or `read-only`), owner, write region, and coordination group.

Before a write, capture a fresh baseline with time and source identity. After the write, record the expected delta, execution result, readback, comparison, recovery posture, and any unexpected-delta disposition. Prefer references, hashes, versions, and redacted summaries over secrets or sensitive exports.

Structural operations on the same target serialize. Additive work may run concurrently only in declared non-overlapping regions. Destructive work requires exercised recovery or an explicit irreversible acknowledgment with recorded safeguards.

## Lifecycle enforcement

`run.json` remains schema 1. New runs receive `protocol_revision: 2`; runs without the field are revision 1 and keep their previous gates. Revision-2 definition, solution, and plan approvals validate dispatch. Handback validates handback. Review acceptance validates acceptance. A failed validation occurs before lifecycle writes and leaves `run.json` and `events.jsonl` unchanged.

Ordinary scouts remain lightweight. A scout that delegates or mutates shared external state supplies the manifest and validates dispatch before work; its conditional archive validation then checks acceptance.
