# Architecture Current-State Review

## Architecture Summary

### Context

Flow's C-lite protocol deliberately keeps lifecycle state small: `run.json` is
the current projection, `events.jsonl` is append-only history, and
`cli/runstate.py` is the only lifecycle writer. Runtime-specific command and
agent files are generated from framework sources under `scaffolds/default/`;
the project overlay holds project context and run artifacts, not copies of the
framework. The approved initiative adds enforceable orchestration safety at
dispatch, handback, and acceptance without adding a workflow lane, agent
launcher, runtime API, or dependency.

The approved direction is architecturally sound. The compatibility-preserving
shape is a separate, versioned orchestration document referenced by the small
lifecycle projection, with a pure validator used by both an explicit read-only
CLI command and revision-aware lifecycle gates.

### Proposed Shape

- `cli/orchestration.py` owns the orchestration domain model and validation:
  JSON loading, explicit shape checks, controlled vocabularies, risk
  calculation, repository-path containment, declared-scope overlap, and
  cumulative stage rules. It returns structured findings and does not print or
  write lifecycle state.
- `cli/runstate.py` remains the lifecycle application service and sole writer.
  It determines a run's protocol revision, assembles the prospective artifact
  projection, calls orchestration validation before any write, then performs
  the existing projection/history write path only after validation succeeds.
- `cli/flow.py` remains transport only: argparse declarations and dispatch for
  `flow run validate-orchestration` plus the existing commands.
- `.flow/runs/<work-id>/orchestration.json` is the detailed, versioned run-local
  contract. `run.json` contains only the artifact pointer and additive
  `protocol_revision`; it does not duplicate assignments, claims, shared-state
  records, or verification data.
- `scaffolds/default/standards/orchestration.md` is the canonical human policy.
  Templates are authoring aids. Existing command sources contain only trigger
  conditions, the exact stage call, and a link to the standard.
- The Claude and Codex adapters continue to generate from the same canonical
  command bodies and shared agent registry. This feature changes generated
  guidance, not the adapter architecture and not runtime permissions.

### Boundary and Data Flow

```text
command/engineer
      |
      | writes run-local briefs, evidence, orchestration.json
      v
flow run validate-orchestration --stage S
      |
      v
cli/flow.py (arguments/output)
      |
      v
cli/orchestration.py (read-only parse + deterministic findings)

flow run transition EVENT --artifact orchestration_manifest=...
      |
      v
cli/runstate.py
      |  1. load current projection
      |  2. build prospective projection in memory
      |  3. derive protocol revision and required stage
      |  4. call cli/orchestration.py
      |  5. refuse without filesystem writes, or persist state/history
      v
run.json + events.jsonl
```

The dependency direction should be one-way:

```text
flow.py -> runstate.py -> orchestration.py -> fsutil.py / stdlib
   \--------------------> orchestration.py
```

`orchestration.py` must not import `runstate.py`. That keeps the flat sibling
module graph acyclic, makes the validator independently testable, and prevents
CLI presentation or lifecycle persistence from leaking into contract rules.

## Current-State Findings

### Lifecycle projection and persistence

- `cli/runstate.py` owns the transition table, artifact/disposition gates,
  legacy summaries, verification, and both lifecycle writes.
- A new canonical run is created only when an event whose source state includes
  `None` succeeds (`start-definition` or `archive-scout`). This is the correct
  point to stamp `protocol_revision: 2`.
- Current `schema_version` is `1` and `verify()` rejects any other value. An
  additive protocol revision therefore avoids falsely claiming that the
  lifecycle JSON shape itself has broken compatibility.
- Existing projections have no protocol revision. Treating absence as revision
  1 preserves their gates without rewriting them. There is no need for a
  migration or backfill.
- Legacy artifact folders are synthesized as `legacy/inferred` on read and are
  not mutated by status, history, or verification. The current transition
  implementation can create a new canonical envelope inside such a directory
  through a `None`-origin event. The phrase "legacy/inferred stays read-only"
  should therefore mean that reads and upgrade checks never convert it as a
  side effect. Prohibiting an explicit start/archive transition would be a new
  compatibility break unless separately chosen and tested.
- Gate refusal currently happens before `_write_run()` and `_append_event()`.
  The orchestration check must stay in that pre-write region to meet the
  byte-for-byte unchanged requirement.
- Projection and history are not a transactional pair: `_write_run()` happens
  before `_append_event()`. That pre-existing crash window is outside the
  approved validation-refusal requirement. This initiative should not broaden
  into a journal/transaction redesign; `flow run verify` already detects the
  resulting mismatch. Record it as inherited risk rather than silently
  claiming full transition atomicity.

### CLI boundary

- `cli/flow.py` explicitly describes itself as argparse and dispatch only.
  Adding the parser, `--stage`, and `--json` there is consistent; validation,
  file reads, and rendering of diagnostics belong in `cli/orchestration.py`.
- Existing command implementations accept argparse namespaces, while domain
  functions in `runstate.py` accept explicit values. Follow the same split:
  `validate_orchestration(...) -> result` for tests/integration and a thin
  `cmd_validate(args)` renderer for the CLI.
- Text and JSON output must derive from the same ordered findings. A finding
  should carry at least code, stage, manifest path, JSON field path,
  assignment/target identity when present, message, and corrective action.
  Stable codes and field paths are the machine contract; prose can remain
  concise.
- The explicit validation command must be read-only. It may check referenced
  paths and parse JSON, but it should never add an artifact pointer, normalize
  the manifest on disk, or create lifecycle state.

### Runtime and sync boundary

- User-level sync reads canonical command Markdown and agent definitions from
  the framework scaffold, then renders native Claude and Codex files and tracks
  them in managed manifests. Project-level adapter generation is retired.
- No new slash command is being added, so the runtime command registry does not
  gain an orchestration lane. Existing registered command bodies change and are
  regenerated through the normal sync path.
- The new Python module ships automatically in release installs because the
  installer copies top-level content using a blacklist and includes `cli/`.
  Release staging/import tests still need to prove the module is self-contained
  and uses only resolvable standard-library/sibling imports.
- `runtime_smoke.py` proves generated static surfaces and explicitly does not
  prove that a client honored runtime grants or model routing. Orchestration
  capability status must preserve the same epistemic boundary: `unknown` is
  not upgraded to `confirmed` merely because a generated agent file exists.
- Equivalent policy across runtimes is best proved by checking the canonical
  command markers in both generated skills plus sync drift. Duplicating the
  full standard into adapter-specific code would create two policy sources and
  should be avoided.

## Compatibility-Preserving Protocol Design

### Protocol revision rules

Use a small helper with explicit semantics:

- no `run.json`: new run, stamp revision 2 only after all gates pass
- existing `run.json` with no `protocol_revision`: revision 1
- existing `protocol_revision: 1`: revision 1
- existing `protocol_revision: 2`: revision 2
- any other value or wrong type: refuse transitions and fail verification

In Python, reject booleans explicitly even though `bool` is a subclass of
`int`. Do not expose a transition flag that upgrades a run. That makes the
compatibility choice durable and prevents accidental retroactive enforcement.

The current dogfood run was created before this feature and has no revision;
it correctly remains revision 1 while implementing revision 2.

### Stage semantics

Stage checks should be cumulative:

- dispatch = base schema + assignment/risk/ownership/capability/concurrency
  checks
- handback = dispatch + output/reconciliation/shared-mutation result checks
- acceptance = handback + claim disposition/provenance/verifier independence
  checks

Cumulative semantics prevent a caller from bypassing earlier invariants by
requesting a later stage directly, simplify lifecycle integration, and make a
single closure gate sufficient for conditional scout orchestration.

For revision-2 gated transitions:

| Transition | Required stage | Additional artifact rule |
|---|---|---|
| `approve-definition` | dispatch | `orchestration_manifest` required |
| `approve-solution` | dispatch | `orchestration_manifest` required |
| `approve-plan` | dispatch | `orchestration_manifest` required |
| `mark-handback-ready` | handback | existing manifest pointer required |
| `accept-review` | acceptance | existing manifest pointer required |

The transition should validate the prospective artifact map, so a manifest
supplied on the same command is visible to the gate. It should resolve the
canonical pointer from that map and reject attempts to replace it with a
different path later in the run unless an explicit amendment rule is added.
Silent pointer replacement weakens auditability.

`archive-scout` needs conditional behavior to preserve low ceremony:

- no orchestration manifest: retain the lightweight scout closure
- orchestration manifest supplied because the scout delegated or mutated
  shared state: run cumulative acceptance validation before closure

The human command contract remains responsible for invoking dispatch before
actual delegation or mutation. Lifecycle approval is a backstop; it cannot
prove when an agent was launched or an external write occurred.

### Manifest parsing and path safety

The validator should parse into project-owned typed structures or disciplined
dictionaries after validating each field. Do not let raw JSON shapes flow
through every rule.

Repository path checks need both lexical and filesystem containment:

1. reject absolute paths and empty paths
2. normalize against the resolved repository root
3. use `Path.resolve(strict=False)` so existing symlink ancestors are followed
4. require the resolved candidate to remain within the resolved root
5. report the declared path, never artifact contents

Use path-aware containment (`Path.is_relative_to` or equivalent), not string
prefix checks. Keep repository filesystem scopes separate from external target
regions. External coordinates do not have filesystem semantics; compare them
only within the same exact target identity using the declared region grammar,
and label this as declaration-level/lexical validation.

Unknown additive object fields should be ignored at every extensible object
boundary. Unknown enum members, missing required fields, wrong scalar/list
types, and ambiguous scope kinds should fail closed. Arrays should reject
duplicate stable IDs because later lookup by ID would otherwise hide one
declaration.

### Risk and verification ownership

Risk must be calculated from controlled hard-trigger and aggravating-factor
sets. The stored classification is an assertion to cross-check, not an input to
the calculation. Reject duplicates so counts cannot be inflated.

For all work, record stable identities for producer, evidence collector, and
verifier plus the verification artifact. For high-risk work, require the
verifier identity to differ from both the producer and evidence collector.
Comparing declared stable IDs is enforceable; determining whether two aliases
refer to the same person or session is not. The standard must require identity
provenance, while the CLI accurately calls its check declaration-level.

Capability validation has the same boundary. Required capabilities must each
have one declared status from `confirmed`, `missing`, or `unknown`; dispatch
fails unless every required capability is confirmed. The CLI validates the
declaration and cited confirmation evidence, not the runtime's hidden grant
state.

### Shared-state safety

Treat shared-state records as an integration boundary, not generic repository
paths:

- exact target identity partitions conflict analysis
- assignment ID establishes writer ownership
- structural/destructive operations on the same target serialize
- additive operations may overlap only when regions are declared disjoint
- baseline, execution result, readback, comparison, recovery posture, and
  unexpected-delta disposition are artifact references checked at handback
- destructive work requires exercised recovery or an explicit irreversible
  acknowledgment with safeguards

Baseline freshness cannot be universally calculated across arbitrary systems
without connectors. Require capture time and source identity and let the
standard define "immediately before" as a provider obligation; the CLI can
check presence and internal ordering only when timestamps are comparable.

## Change Surface

### New files/modules

- `cli/orchestration.py`
- `scaffolds/default/standards/orchestration.md`
- `scaffolds/default/templates/agent-brief.md`
- `scaffolds/default/templates/orchestration-manifest.md`
- `scaffolds/default/templates/findings-reconciliation.md`
- `scaffolds/default/templates/external-mutation-record.md`
- `docs/adr/<number>-separate-orchestration-contract-from-lifecycle-state.md`

### Modified files/modules

- `cli/runstate.py`: revision interpretation and pre-write stage gates
- `cli/flow.py`: parser and dispatch only
- `tests/test_flow.py`: validator, lifecycle compatibility, refusal atomicity,
  release staging, CLI, and generated-surface coverage
- applicable canonical command sources under `scaffolds/default/commands/`
- collaboration/evidence standards and handoff/run templates
- `scaffolds/default/flow.toml`: CLI help catalog only if the generated command
  table needs the new subcommand named explicitly
- maintainer and user documentation named in the approved plan
- `cli/runtime_smoke.py` only if a small canonical marker check is needed to
  prove both generated runtime skills carry the policy

### Data model / migration impact

- additive `protocol_revision` in newly created lifecycle projections
- new versioned run-local `orchestration.json`
- no rewrite, backfill, or migration for existing canonical or legacy runs
- no external database/schema migration

## Risks and Tradeoffs

### Main tradeoffs

- Separating orchestration detail keeps lifecycle state stable and reviewable,
  but creates a referential-integrity boundary between `run.json` and
  `orchestration.json`. Stage gates and path checks are the compensating
  control.
- Explicit JSON enables deterministic enforcement and forward compatibility,
  but increases authoring cost. Complete templates and field-specific
  diagnostics are necessary product behavior, not optional polish.
- Declaration-level validation is portable across runtimes and external
  systems, but cannot prove actual permissions, identity equivalence, semantic
  truth, or external coordinate disjointness. Diagnostics and documentation
  must not overstate certainty.
- Cumulative stage validation is slightly more work per later gate, but the
  artifacts are local and small; correctness and bypass resistance dominate
  negligible latency.

### Failure and migration risks

- **Accidental retroactive gating:** defaulting a missing revision to 2 would
  strand active runs. Absence must mean revision 1.
- **Validation after mutation:** updating/writing lifecycle files before the
  orchestration result is known violates refusal atomicity. Validate the
  in-memory prospective projection first.
- **Mutable manifest pointer:** silently changing the pointer between phases
  makes earlier approvals unverifiable. Make it immutable or require a future
  explicit amendment event.
- **Symlink escape:** lexical `..` checks alone do not keep referenced paths in
  the repository. Resolve existing symlink ancestors.
- **String-prefix overlap bugs:** `/a/b` is not an ancestor of `/a/beta`.
  Compare normalized path components or declared region segments.
- **Identity theater:** distinct display strings do not prove independent
  humans/providers. Require provenance and describe CLI results as declared
  independence.
- **Instruction drift:** copying detailed policy into six lane commands will
  produce contradictions. Keep one standard and minimal command triggers.
- **Flat-module cycle:** importing runstate from orchestration would couple
  validation to persistence and can break direct-module tests/release imports.
- **Overbroad atomicity claim:** validation refusal can be byte-preserving even
  though an OS failure between the two existing lifecycle writes remains
  possible. State the narrower guarantee.

### Operational concerns

- Validation is local, dependency-free, and proportional to small run
  artifacts; scaling and latency risk are negligible.
- Diagnostics must contain paths, identities, codes, and corrective actions but
  never embed baseline/evidence contents or secrets.
- Re-running a stage check is naturally idempotent because it is read-only.
  Lifecycle transitions retain their existing state-based duplicate refusal.
- Release proof must exercise the staged/released tree, because a development
  checkout can hide a missing module from packaging/import coverage.
- Generated-runtime smoke can prove policy presence and routing declarations,
  not runtime grant enforcement. Manual runtime evidence remains correctly
  separate.

## ADR Recommendation

- Needed: yes
- Title: Separate orchestration contracts from C-lite lifecycle state
- Decision to capture: Keep schema-1 `run.json` as the small lifecycle
  projection; add an additive protocol revision and a referenced, versioned
  `orchestration.json`; enforce it through a pure stage-aware validator called
  explicitly before operations and as a pre-write lifecycle backstop; preserve
  revision-1 and legacy behavior without migration.
- Alternatives to record:
  - expand `run.json` with assignments/shared-state/evidence: rejected because
    it couples detailed evolving policy to the stable lifecycle projection
  - create a new orchestration lane/command/runtime: rejected because it
    duplicates existing lanes and exceeds Flow's adapter role
  - prose-only guidance: rejected because unsafe overlap, missing evidence, and
    inconsistent risk remain structurally unenforced
  - bump `run.json` schema and migrate all runs: rejected because the lifecycle
    shape is still compatible and retroactive migration can strand active work

## Implementation Guardrails

1. Keep `orchestration.py` pure apart from explicit reads; no printing in its
   domain functions and no lifecycle writes.
2. Derive all text/JSON diagnostics from one ordered result model.
3. Validate cumulative stages against the prospective artifact projection
   before `_write_run()` or `_append_event()`.
4. Treat missing protocol revision as 1 forever; stamp 2 only on successful new
   runs.
5. Do not claim runtime capabilities, semantic truth, identity equivalence, or
   external-coordinate safety beyond what declarations and referenced evidence
   can establish.
6. Preserve one canonical orchestration standard; generated surfaces remain
   outputs.
7. Test the released/staged module graph and generated Claude/Codex surfaces,
   not only direct unit functions in the checkout.
