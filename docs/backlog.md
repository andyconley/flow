# Backlog

## Purpose

This file tracks open work only. It should help a maintainer choose the next
flow capability to define, plan, or build.

Completed work belongs in `CHANGELOG.md`. Project-specific migration notes
belong in that project's overlay or in a separate adoption case study.

The active list is ordered. Move an item when its priority changes.

## Active Priorities

### 1. Existing-Project Adoption Playbook

Status: not started

Problem:

- existing projects already have workflow notes, runtime folders, project
  memory, and local habits
- `flow setup project` handles a clean scaffold, but it does not tell someone
  how to migrate an existing project safely

Include:

- inventory the current project
- decide what becomes `.flow` source
- scaffold `.flow`
- move canonical materials
- generate runtime adapters
- verify the migration
- choose between a structured chat summary and a durable migration artifact

Adoption is done only when the repo has evidence that:

- `.flow` contains the source of truth
- generated runtime files match the expected surfaces
- unmanaged files are intentionally preserved
- collaborators know where to edit
- README, help, and docs describe the adopted runtime model

Why it matters:

- adoption should feel boring and reversible
- agents should not rebuild the process from memory each time

Next step:

- write `docs/adoption-playbook.md`, then link it from README and this backlog

### 2. Runtime Surface Inventory and Reconciliation

Status: not started

Problem:

- flow can generate files into `.claude/`, `.agents/skills/`, and `.codex/`
- existing projects may already have files in those locations
- the user needs to know what flow would touch before any write happens

The inventory should classify each runtime file:

- move into `.flow` source
- keep runtime-local and unmanaged
- replace with generated flow output
- remove after migration

It should also detect overlaps between generated flow paths and existing
unmanaged files.

Why it matters:

- a read-only report turns adoption risk into a list
- runtime-neutral inventory keeps the model honest across Claude and Codex

Next step:

- define a read-only `flow adopt inventory` command or equivalent report
- defer import/write behavior until the report is useful

### 3. Drift Reporting With Next Actions

Status: partial

Current:

- `flow sync <target> --check` reports changed, stale, and conflicting files
- `flow doctor` reports sync state and drift status

Problem:

- the current output tells the user that drift exists
- it does not always tell the user what caused it or what to do next

Improve the output so it names:

- source-changed updates
- stale managed files
- merge-protected runtime config
- unmanaged conflicts
- the likely next command or manual action

Why it matters:

- existing-project adoption needs operator guidance beyond status labels
- clear drift output reduces edits to generated files and accidental deletion
  of runtime-local configuration

Next step:

- improve `--check` output before adding new adoption commands; it is already
  the first diagnostic surface

### 4. Content-Aware Project Refresh

Status: partial

Current:

- `flow refresh project` copies only missing scaffold files

Problem:

- project overlays drift when framework templates change
- flow does not yet show whether a copied project file is behind the framework

Need:

- detect framework template changes after a project copied the templates
- compare project files to newer template versions without overwriting local
  edits
- surface recommended merges, conflicts, and "leave local" decisions

Why it matters:

- users should be able to update framework guidance without losing local
  project choices
- missing-file refresh is safe, but it does not help when copied files change

Next step:

- define the comparison model: baseline metadata, content hashes, three-way
  diff, or advisory-only heuristics

### 5. Project Override and Exclusion Model

Status: not started

Problem:

- existing projects may want flow, but not every generated command, agent,
  hook, or runtime target
- deleting generated files is a bad opt-out because drift checks will keep
  finding them

Let a project declare:

- do not generate this command
- do not generate this agent
- do not register this hook
- generate only selected runtime targets

Make exclusions visible in doctor and check output.

Why it matters:

- adoption works better when projects can take the parts they need
- explicit exclusions make that choice visible and repeatable

Next step:

- define the manifest shape and precedence rules before implementation

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
