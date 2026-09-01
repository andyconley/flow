# Orchestration Safety Contract Implementation Plan

## Context

Flow already provides lifecycle gates, role routing, durable run artifacts, evidence inventories, and separate implementation and review lanes. It does not yet enforce the contracts at the joints between those pieces. This initiative adds enforceable orchestration safety without adding a new command, agent runtime, or lifecycle phase.

The implementation will be developed in the isolated `codex/orchestration-safety` worktree based on `origin/main` at `v0.20.2`. The unrelated `docs/backlog.md` changes in the canonical checkout are outside this work and must never be staged, copied, reverted, or included in the release.

## Approved decisions

1. Orchestration safety is a shared standard consumed by existing Flow lanes.
2. Detailed orchestration state lives in a versioned run-local JSON artifact; `run.json` remains the small lifecycle projection.
3. CLI validation is structural and phase-aware. It validates declarations, controlled vocabulary, referenced artifact existence, and internally detectable conflicts. It does not claim access to hidden runtime grants or semantic truth.
4. Capability state is `confirmed`, `missing`, or `unknown`. A required capability must be confirmed before dispatch; unknown is not proof.
5. Risk is calculated from controlled trigger lists. It is not author-declared free text.
6. High-risk work requires a verifier distinct from the producer and evidence collector whose evidence is being certified.
7. Existing C-Lite and legacy runs cannot be stranded by an upgrade.
8. Shared repository work uses Git as its baseline. Shared external systems require a fresh read or export immediately before mutation and a post-write readback and comparison.
9. The Flow repository will keep a minimal project overlay and use this run to dogfood its own lifecycle.

## Artifact contract

### Canonical machine artifact

Each enforced run uses:

```text
.flow/runs/<work-id>/orchestration.json
```

The JSON document contains these top-level fields:

- `schema_version`: orchestration artifact schema, initially `1`
- `work_id`: must equal the containing run id
- `mode`: `single`, `delegated`, or `shared-mutation`
- `risk`: hard triggers, aggravating factors, calculated classification, and rationale
- `assignments`: provider briefs, capabilities, ownership, outputs, and success criteria
- `shared_state`: targets, mutation types, write scopes, serialization, and evidence paths
- `reconciliation`: readable artifact path and resolution status
- `verification`: producer, evidence collector, verifier, independence, and artifact path

Unknown additive object fields are ignored for forward compatibility. Unknown enum values, type mismatches, unsafe paths, and missing required fields fail closed.

### Assignment fields

Every assignment declares:

- stable assignment id
- lane and role/provider identity
- human-readable brief path
- input evidence paths
- read scopes
- write scopes, or explicit read-only status
- required capability names
- capability status for each required capability
- output path and format
- success criteria
- claim-status expectation
- concurrency or serialization group

Repository paths are normalized relative to the repository root and may not escape it. A declared output must sit within a declared write scope. For path scopes, equality and ancestor/descendant relationships count as overlap. External regions are compared only within the same declared target; the CLI must state that this is declaration-level validation rather than semantic coordinate analysis.

### Claim statuses

Material claims use:

- `observed`: directly supported by cited source or command evidence
- `inferred`: conclusion linked to supporting observations
- `recommended`: proposed normative choice
- `unverified`: plausible but not checked

A material claim is one that influences scope, safety, a contract, validation, a disposition, or a release assertion. An observed condition cannot become a requirement without a cited source or recorded decision.

### Risk calculation

Hard-trigger enum values:

- `destructive_or_irreversible`
- `production_or_shared_external_mutation`
- `security_or_privacy_boundary`
- `loss_bearing_data_migration`
- `regulated_personnel_safety_or_customer_access`

Aggravating-factor enum values:

- `large_blast_radius`
- `weak_rollback`
- `weak_or_delayed_observability`
- `concurrency_or_cross_system_coordination`
- `material_unresolved_ambiguity`
- `author_only_validation`
- `unverified_claim_for_durable_truth`

Any hard trigger produces `high`; otherwise two or more aggravating factors produce `high`; zero or one produces `standard`. The validator calculates the result and rejects a conflicting stored classification.

### Shared-state records

Each shared target declares:

- target id, kind, and exact identity
- mutation type: `additive`, `structural`, `destructive`, or `read-only`
- assignment owner and write region
- concurrency or serialization group
- baseline artifact, capture time, and source identity
- expected delta
- recovery state: `exercised`, `available_unexercised`, or `irreversible_acknowledged`
- execution-result artifact
- post-write readback and comparison artifacts
- unexpected-delta status and disposition

Structural operations on the same target serialize. Additive operations may be concurrent only in declared non-overlapping regions. Destructive work requires an exercised recovery path or an explicit irreversible acknowledgment plus recorded safeguards.

## CLI design

### New module

Add `cli/orchestration.py`, using only Python's standard library. It owns:

- manifest loading and schema validation
- controlled vocabulary
- risk calculation
- safe path normalization
- scope-overlap detection
- phase-aware validation
- stable text and JSON diagnostic payloads

Keep parsing and validation independent from CLI printing so unit tests can exercise it directly.

### New command

Add:

```bash
flow run validate-orchestration <work-id> \
  --stage dispatch|handback|acceptance \
  [--json]
```

Stages validate:

- `dispatch`: manifest shape, brief existence, input evidence, required capabilities, output location, ownership, and static concurrency conflicts
- `handback`: declared outputs, reconciliation, mutation execution results, baseline, recovery posture, readback, comparison, and unexpected-delta disposition
- `acceptance`: claim reconciliation status, identity provenance, verifier independence, and verification evidence

Diagnostics identify the manifest path, JSON field, assignment or target, violated rule, and corrective action. Text and JSON modes use the same underlying findings.

### Lifecycle integration

- Keep `run.json` schema version `1`.
- Add `protocol_revision` to new run projections. Runs created after this feature default to revision `2`.
- Existing runs without `protocol_revision` are revision `1` and retain existing gates.
- `legacy/inferred` stays read-only and valid.
- Revision-2 `approve-definition`, `approve-solution`, and `approve-plan` require the persisted `orchestration_manifest` artifact and re-run dispatch validation.
- Revision-2 `mark-handback-ready` re-runs handback validation before writing lifecycle state.
- Revision-2 `accept-review` re-runs acceptance validation before writing lifecycle state.
- `flow-scout` remains lightweight. If it delegates or mutates shared external state, it creates the standard manifest, runs explicit stage checks, and supplies the manifest to `archive-scout` for conditional validation.
- Any validation failure leaves both `run.json` and `events.jsonl` byte-for-byte unchanged.

Commands must direct the orchestrator to run dispatch validation immediately before spawning or mutating. Gate validation is the backstop, not the first detection point.

## Documentation and template changes

### New sources

- `scaffolds/default/standards/orchestration.md`
- `scaffolds/default/templates/agent-brief.md`
- `scaffolds/default/templates/orchestration-manifest.md`
- `scaffolds/default/templates/findings-reconciliation.md`
- `scaffolds/default/templates/external-mutation-record.md`
- `docs/adr/` entry: separate orchestration contracts from lifecycle state

The orchestration standard is canonical. Commands carry only trigger conditions, required stage calls, and links to the standard to avoid instruction duplication.

### Existing sources to update

- `scaffolds/default/commands/flow-define.md`
- `scaffolds/default/commands/flow-solution.md`
- `scaffolds/default/commands/flow-plan.md`
- `scaffolds/default/commands/flow-implement.md`
- `scaffolds/default/commands/flow-review.md`
- `scaffolds/default/commands/flow-scout.md`
- `scaffolds/default/standards/collaboration.md`
- `scaffolds/default/standards/evidence.md`
- `scaffolds/default/templates/implementation-handoff.md`
- `scaffolds/default/templates/run-template.md`
- `scaffolds/default/FRAMEWORK.md`
- `README.md`
- `docs/architecture.md`
- `docs/file-structure.md`
- `docs/cli-reference.md`
- `docs/runtime-adapters.md` if generated-surface behavior needs clarification

### CLI and tests to update

- `cli/orchestration.py` — new
- `cli/runstate.py`
- `cli/flow.py`
- `tests/test_flow.py`
- release-staging/import coverage where needed for the new module

`scripts/regenerate-flow-help.py` is changed only if the command catalog or generated help content requires it; otherwise run its check without modifying it.

## Implementation slices

### Slice 1 — Contract and ADR

1. Write the orchestration standard with the approved brief, claim, reconciliation, shared-state, risk, and verification rules.
2. Add the four readable templates plus the machine-manifest authoring template.
3. Record the ADR and update collaboration/evidence standards to point to the canonical orchestration rules.
4. Add lightweight command references without enforcement calls yet.
5. Review for duplicated or contradictory guidance.

Exit evidence: templates can express a single-provider run, delegated read-only review, disjoint concurrent work, serialized shared mutation, and high-risk external mutation.

### Slice 2 — Validator and schema

1. Implement manifest parsing, type checks, enum checks, risk calculation, path safety, overlap checks, and phase rules.
2. Wire the explicit CLI command and JSON output.
3. Add focused tests for every rule and error path.
4. Ensure diagnostics never expose artifact contents or sensitive baseline data.

Exit evidence: positive fixtures pass; each required negative case fails with a stable field-specific diagnostic.

### Slice 3 — C-Lite integration and compatibility

1. Stamp protocol revision on newly created runs.
2. Preserve revision-1 and legacy behavior.
3. Add conditional orchestration artifacts and stage checks to lifecycle transitions.
4. Prove atomic refusal by comparing lifecycle files before and after every failing gate family.
5. Add a complete revision-2 lifecycle integration test.

Exit evidence: new runs fail closed where required; pre-existing runs still transition and verify under their original contract.

### Slice 4 — Workflow and documentation integration

1. Update all applicable commands with dispatch timing, shared-state escalation, claim reconciliation, and acceptance behavior.
2. Update handoff and run templates.
3. Update architecture, file model, CLI reference, README, runtime-adapter notes, and help output where applicable.
4. Regenerate or resync Claude and Codex adapters from canonical sources.
5. Verify the two runtime surfaces express equivalent policy without hard-coding runtime-specific model names into command prose.

Exit evidence: source docs, CLI help, generated skills, and generated agent routing agree.

### Slice 5 — End-to-end review and release

1. Run targeted, full, generated-surface, installation, and release-staging checks.
2. Run structured acceptance review against these requirements and acceptance criteria.
3. Fix findings and repeat affected checks.
4. Re-fetch `origin/main`; integrate only by fast-forward or rebase without force-pushing.
5. Inspect `git remote -v`, staged files, and final diff. Confirm the canonical checkout's backlog edits are absent.
6. Commit logical changes with Conventional Commits. Ensure at least one `feat:` commit so the pre-1.0 release is minor.
7. Push the reviewed commit to `main` and wait for semantic-release.
8. Verify the new tag, changelog entry, GitHub release, and non-empty rendered notes.
9. Install or update from the released tag in an isolated home, sync both runtimes, and run runtime smoke.
10. Record release evidence before reporting publication complete.

Exit evidence: the released artifact, not only the development checkout, passes installation and runtime checks.

## Explicit exclusions

- No new orchestrator command or lifecycle phase.
- No general-purpose task scheduler, workflow engine, or recurring-operations lane.
- No runtime API for launching agents.
- No automatic snapshots, rollbacks, credentials, or connectors for arbitrary external systems.
- No automated semantic truth, fabrication, or conflict-of-interest detection.
- No retroactive conversion or gating of existing runs.
- No changes to the unrelated canonical-checkout backlog work.

## Risks and mitigations

- **Instruction growth:** keep shared detail in one standard; commands contain only triggers and gate calls.
- **False capability confidence:** represent inaccessible runtime state as unknown and fail required unknown capabilities before dispatch.
- **Lexical overlap limits:** state the limitation in diagnostics and require human review for external coordinate aliases.
- **Sensitive baseline evidence:** record references, hashes, versions, and redacted summaries rather than secrets or full sensitive exports.
- **Upgrade stranding active work:** gate only revision-2 runs and preserve revision-1 behavior.
- **JSON authoring friction:** provide a complete template, precise diagnostics, and small low-risk examples.
- **Release race:** fetch immediately before integration and never force-push.
- **Release automation failure after push:** verify workflow, tag, release, and notes; repair forward rather than rewriting published history.

## Review composition

- Lead developer: implementation sequencing and code ownership
- Test engineer: validator, atomicity, compatibility, and release proof
- Quality reviewer: requirement fit and pre-acceptance verdict
- Tech writer: durable docs and handback
- Architect: lifecycle/artifact boundary and ADR
- Security reviewer: shared-state evidence, sensitive artifacts, destructive and authorization-related cases

The final high-risk external-mutation fixture must be accepted by a provider that did not produce the implementation or its evidence.
