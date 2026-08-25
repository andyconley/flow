# Backlog

## Purpose

This file tracks open work only. It should help a maintainer choose the next
flow capability to define, plan, or build.

Completed work belongs in `CHANGELOG.md`. Project-specific migration notes
belong in that project's overlay or in a separate adoption case study.

The active list is ordered. Move an item when its priority changes.

## Active Priorities

### 1. C-Lite Workflow Enforcement

Status: archived

Problem:

- flow has strong lane contracts, but the actual run state is still mostly
  prose and agent discipline
- status, resume, archive readiness, and gate completion depend on interpreting
  Markdown and chat context rather than a runtime-neutral state record
- Claude and Codex need the same project truth when work crosses sessions or
  runtimes

Include:

- `run.json` as the canonical current run state
- `events.jsonl` as append-only transition history
- a small state machine for critical lane gates, not full orchestration
- `flow run list/status/history/verify/transition`
- `/flow-status` and `/flow-resume` reading run state before falling back to
  legacy inference
- durable define -> solution -> plan -> implement -> review -> archive handoffs
- a scout escalation envelope so small work can grow without losing context
- explicit lane boundaries, especially implementation self-review versus
  independent acceptance review

Done only when:

- a run can be listed, inspected, verified, paused/resumed, and archived from
  the CLI
- lane commands write or update the run state as they move through gates
- invalid critical transitions fail with actionable missing requirements
- legacy runs remain readable or explicitly marked as legacy/inferred
- docs, help, and tests describe the new run protocol

Why it matters:

- guardrails should not depend on a runtime remembering prompt instructions
- the right state should be inspectable after compaction, interruption, or
  runtime handoff
- this gives flow enforcement without turning it into a heavy workflow engine

Next step:

- run `/flow-plan` for C-lite workflow enforcement

### 2. Runtime Neutrality and Cross-Runtime Behavior

Status: archived

Problem:

- shared workflow commands are intended to be runtime-neutral, but some
  continuity assumptions still point at Claude-specific memory or checkpoint
  surfaces
- generated files can be checked statically, but runtime command discovery and
  role behavior still need real smoke evidence

Include:

- remove Claude-specific continuity assumptions from shared command bodies
- introduce runtime-specific context-provider wording or generated sections for
  Claude and Codex
- prove generated commands and agents actually load in both runtimes
- verify configured role agents use intended model and effort where the runtime
  supports it
- add cross-runtime workflow smoke tests around boot, define, plan, review,
  archive, status, and resume
- keep project artifacts canonical; runtime memory is a cache or companion, not
  the workflow source of truth

Why it matters:

- flow's value is portability across supported AI runtimes
- runtime-specific memory assumptions make cross-runtime handoff accidental

Next step:

- closed by `20260823-runtime-neutrality-cross-runtime`; manual runtime smoke
  remains optional follow-up evidence when real client proof is needed

### 3. Maintainer Supportability

Status: not started

Current:

- `flow doctor`, `flow help`, `flow sync ... --check`, and `flow update --check`
  provide good first-line diagnostics
- several failure classes still collapse into broad messages or advisory output

Problem:

- a maintainer still has to manually collect too much evidence to classify a
  failure
- `flow doctor` is human-friendly, but it is not a strict gate or structured
  support artifact
- update, sync, and runtime drift failures need clearer cause and next-action
  guidance

Include:

- `flow doctor --json` or `flow support bundle`
- stable diagnostic categories such as `missing`, `parse_error`,
  `permission_denied`, `git_unavailable`, `remote_unreachable`,
  `manifest_invalid`, `managed_conflict`, and `runtime_not_found`
- `flow doctor --check` or `--strict` with useful nonzero exits for actionable
  failures
- better `flow update` remote/tag/changelog failure classification
- rollback or previous-version recovery path for release installs
- sync drift output that names cause, target root, source manifest, conflict
  category, and next action
- a maintainer incident macro covering commands, cwd, install mode, source
  revision, stderr, affected runtime, and last known good version

Why it matters:

- support should start with one structured evidence bundle, not ten remembered
  commands
- Flow is local and personal, so diagnosability is the operational safety net

Next step:

- plan the support bundle and diagnostic status model

### 4. Telemetry and Usage Freshness

Status: not started

Current:

- usage tracking has a real store and good collector coverage
- `flow cost active` harvests and normalizes Claude data automatically
- Codex harvest is still manual before summary/trend views are current

Problem:

- cost and capacity reports can be stale or empty unless the maintainer
  remembers the right harvest/normalize path
- hook behavior, plugin usage, cost reads, and freshness signals are not yet
  presented as one supportable pipeline

Include:

- make Codex harvest freshness less hidden
- clarify which cost commands harvest automatically and which read stored data
- improve freshness/staleness reporting in cost and plugin usage views
- add hook-to-telemetry integration tests
- add plugin usage CLI boundary tests
- decide whether a safe `flow cost refresh` command should run harvest and
  normalize for both supported runtimes

Why it matters:

- telemetry should reduce session-management overhead, not add another hidden
  maintenance ritual
- stale usage data is worse than no usage data when it looks current

Next step:

- plan the freshness model and the smallest command surface that makes it
  obvious

### 5. Adoption and Project Migration

Status: not started

Problem:

- existing projects already have workflow notes, runtime folders, project
  memory, and local habits
- `flow setup project` handles a clean scaffold, but it does not tell someone
  how to migrate an existing project safely
- existing projects may want flow, but not every generated command, agent,
  hook, or runtime target
- deleting generated files is a bad opt-out because drift checks will keep
  finding them
- older backlog and docs still carry some project-sync/project-refresh framing
  that needs reconciliation with the current user-level runtime model

Include:

- existing-project adoption playbook
- read-only runtime surface inventory and reconciliation report
- explicit project override/exclusion model
- project setup -> migration -> doctor convergence workflow
- classification of runtime files: move into `.flow` source, keep unmanaged,
  replace with generated output, or remove after migration
- docs cleanup for retired project-sync and project-refresh assumptions
- README, help, and docs that describe the adopted runtime model after the
  C-lite run protocol is defined

Make exclusions visible in doctor and check output.

Why it matters:

- adoption should feel boring, reversible, and inspectable
- adoption works better when projects can take the parts they need
- explicit exclusions make that choice visible and repeatable

Next step:

- plan after C-lite so adoption guidance does not immediately go stale

## Deferred / Watch

### Agent and Standards Review

Status: deferred from initial scaffold review

Review the role agents and standards when a specific role, standard, or command
starts causing friction.

Watch for:

- role prompts that no longer match current flow behavior
- standards that are too broad, duplicated, or stale
- gaps around `flow-define`, research behavior, review behavior, and
  cross-runtime wording

Do not prioritize until:

- real usage points to a specific role or standard that needs work

### Stacked Overlay CLI Support

Status: prose contract only

Current:

- command contracts describe stacked overlays: reads merge from ancestor
  `.flow/` directories, and writes go to the most-specific overlay
- the CLI does not yet expose a shared overlay traversal or merge API

Keep watching because:

- deterministic CLI support would help if commands need machine-readable
  overlay state, automated validation, or non-agent consumers

Do not prioritize until:

- a concrete workflow needs the CLI to own stacked overlay resolution

### Engagement-Discipline Abstraction

Status: pattern shipped, abstraction deferred

Current:

- hard-gated engagement patterns are duplicated across the heavier workflow
  commands and the solution-architect agent

Keep watching because:

- duplicated process text can drift as flow evolves

Do not prioritize until:

- another command needs the same pattern, or updating the existing pattern
  becomes repetitive enough to cause mistakes

### Future Runtime Agent Strategy

Status: Claude and Codex implemented; future runtimes undecided

Current:

- Claude receives generated skills, agents, hooks, settings, and a managed
  manifest
- Codex receives generated skills, native agents, hooks, hooks.json, and a
  managed manifest

Keep watching because:

- another runtime may need a different split between commands, role prompts,
  hooks, and generated configuration

Do not prioritize until:

- flow has a concrete third runtime to support

### Self Attested Validation Has No Standard

Status: observed 3 times, promoted from the capability-gap ledger

Every lane asks for validation evidence and none asks where the evidence came from. A test count typed by the author of the change is accepted at the same weight as one from a run anyone can re-inspect. The evidence standard now covers whether proof could have failed, but not whether the party reporting it had an interest in the answer.

Second sighting. Every validation figure in this run was a local run by the author of the change, and the run's own artifacts state so in four separate places without any lane offering a way to resolve it. A lane that asks for evidence but accepts author-produced evidence at full weight turns the caveat into boilerplate: it gets written honestly, read past, and changes nothing.

Third sighting. A slice adding a destructive command shipped on figures the change's own author produced, with no mechanism in the repository capable of producing any other kind. The caveat was written into the validation record, the pull request body, and the commit message, and changed nothing about whether the work merged.

### Agent Brief Exceeds Tool Grant

Status: observed 2 times, promoted from the capability-gap ledger

Commands brief role agents to write artifacts to the run directory, but nothing reconciles a brief against what the agent can actually do. Two independent causes with the same silent outcome: roles defined without a write tool, and roles sandboxed away from the run directory by worktree isolation. Six sightings in one session, including the orchestrator itself. Nothing failed loudly in any case; each agent mentioned it in prose and the files were moved by hand afterwards. The framework has no declaration of what a role can write and no check that a brief stays inside it.

Second sighting. A judgment-tier review role was briefed to record findings in a durable artifact but held read-only tools, so the findings came back inline and the orchestrator transcribed them by hand. The brief and the grant are authored in different places and nothing compares them, so the mismatch surfaces only as prose inside the agent's reply.

### Cross Slice Deferrals Have No Carrier

Status: observed 2 times, promoted from the capability-gap ledger

A review finding can be dispositioned as partially accepted with the remainder explicitly assigned to a later slice, and nothing carries it there. Observed: a finding deferred by name to the next slice, whose own review closed neighbouring items and never mentioned it. Dispositions are per-slice documents, so a deferral is written down in the one place the next slice does not read.

Second sighting, and wider than the first. The first was a review finding deferred to a later slice; this was a plan item assigned to a slice that shipped without it, caught only because a reviewer happened to compare the plan against the diff. Any document that assigns work forward — plan, disposition, handback — is written in the one place the receiving step does not read, and nothing reconciles them.

### Mutation Survivors Have No Triage Guidance

Status: observed 2 times, promoted from the capability-gap ledger

The implement lane asks whether a mutation check ran but gives no guidance for reading the result: a surviving mutant most often means the fixture cannot reach the code, not that coverage is absent, and mutually redundant guards survive individually while being covered jointly. Both cases were misread as missing coverage.

Second sighting, and the diagnosis in the first is confirmed. Four mutants survived their first attempt across two rounds; two were unreachable in the fixture that appeared to cover them rather than uncovered. Reading a survivor as missing coverage would have added a redundant test and left the real hole — a covering test asserting against the wrong fixture — in place. The lane asks whether the check ran and still says nothing about how to read the result.

### No Lane Prompts For Archive

Status: observed 2 times, promoted from the capability-gap ledger

Archive is deliberately human-invoked, but no lane tells the engineer to run it and no lane can trigger it. A run therefore completes with its handback intact and its capability gaps never captured, silently. The gap-capture loop depends on a step that nothing in the phase machine asks for.

Second sighting. Four slices were planned, implemented, reviewed, merged, and released across several days before the closing lane ran, and it ran only because the engineer asked for it directly. The handbacks recommended it each time, which is the orchestrator compensating rather than the phase machine working. Nothing in a lane triggers the step that captures gaps, so the corpus depends on the engineer remembering.

### No Lane For Recurring Operational Runs

Status: observed 3 times, promoted from the capability-gap ledger

Every execution lane assumes a change to a repository that lands in a commit. A recurring operational run collects from several sources, produces judgement-bearing output, and writes to an external system of record where each write is immediately visible to other people and not revertible by any repository operation. It has no lane, no run-artifact home, and no place to record what was written where.

Second sighting. The absence of a run-artifact home for operational work is what made the errors expensive: reconstructing what a prior run wrote to an external system required re-reading that system, and three wrong writes surfaced only because a person happened to open one record. A lane that writes outward needs a durable record of what it wrote, which is exactly what no lane provides.

Third sighting, and a one-off rather than a recurring run, which shows the gap is not about recurrence but about direction of write. Work that began as a read-only question escalated mid-session into an irreversible write to an external system of record. There was no run, no work id and no artifact home at any point, and the escalation from question to production change crossed no gate, because no lane exists for work whose output is not a commit.

### Role Output Not Verified Before Durable Use

Status: observed 3 times, promoted from the capability-gap ledger

Role agents return confident, specific, fabricated detail and nothing in the framework requires the orchestrator to check it before it lands in a durable record. Observed on two of three roles in a single closing lane: invented command flags, invented counts, and an invented failure mode, all written in the register of verified fact. The lower-cost tiers are the likeliest to fabricate and are also the tiers assigned to the roles whose output is meant to be durable. No lane distinguishes a claim a role read from one it produced.

Role agents stated inferences in the register of fact; nothing in the lane requires their claims be checked against source before entering a durable artifact.

Third sighting. A mechanical-tier role was given a brief of verified facts and told not to invent, and still promoted a descriptive observation into a hard requirement - reporting an incidental property of one client's request as a constraint the server imposes. The distortion was not invention but modal drift: an is restated as a must. Briefing a role with correct facts does not constrain the register it writes them in, and nothing in the lane checks that the strength of a claim survived the round trip.

### Destructive Work Has No Recovery Verification Gate

Status: observed 2 times, promoted from the capability-gap ledger

A lane will accept a slice that adds a file-deleting command on fixture tests and a dry run alone. Nothing asks whether the recovery path was exercised, so a command shipped with its restore route asserted by a test of the backup's contents and never once walked end to end. The verification happened afterwards, because the engineer asked for it, and it passed — but nothing in the phase machine would have noticed if it had not. Deletion and recovery are one feature and only one of them has an evidence requirement.

Second sighting, and the inverse case: the destructive step had no recovery path at all. An irreversible production deletion was carried out behind pre-flight identity checks, an abort gate on dependent records, an ordering constraint, and a post-verification query - every one of which the orchestrator invented, because no lane requires them and no standard says an action with no undo must establish that fact before it runs. The engineer had to ask to be checked with at each step; nothing in the phase machine would have asked on its own.
