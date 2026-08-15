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

Build a playbook for adopting flow in a repo that already has local workflow
rules, runtime folders, and project memory.

Include:

- inventory of existing project and runtime content
- source-of-truth classification
- `.flow` scaffolding
- migration of canonical materials
- runtime adapter generation
- adoption verification
- guidance on structured chat summaries versus durable migration artifacts

The verification checklist belongs in this playbook. Adoption is done only when
the repo has evidence that:

- `.flow` contains the source of truth
- generated runtime files match the expected surfaces
- unmanaged files are intentionally preserved
- collaborators know where to edit
- README, help, and docs describe the adopted runtime model

Why it matters:

- fresh-project setup and existing-project adoption are different workflows
- agents should not have to reconstruct the adoption sequence from memory

Next step:

- write `docs/adoption-playbook.md`, then link it from README and this backlog

### 2. Runtime Surface Inventory and Reconciliation

Status: not started

Create a read-only inventory for existing runtime surfaces before flow writes
generated files beside them.

Classify files across `.claude/`, `.agents/skills/`, and `.codex/` as:

- move into `.flow` source
- keep runtime-local and unmanaged
- replace with generated flow output
- remove after migration

Also detect overlaps between generated flow paths and existing unmanaged files.

Why it matters:

- generation is not enough for repos that already have runtime-specific content
- a runtime-neutral inventory keeps adoption from being anchored to one runtime

Next step:

- define a read-only `flow adopt inventory` command or an equivalent report;
  defer import/write behavior until the report is useful

### 3. Content-Aware Project Refresh

Status: partial

Current:

- `flow refresh project` copies only missing scaffold files

Need:

- detect framework template changes after a project copied the templates
- compare project files to newer template versions without overwriting local
  edits
- surface recommended merges, conflicts, and "leave local" decisions

Why it matters:

- project overlays drift from the framework over time
- missing-file refresh is safe, but it does not help when copied files change

Next step:

- define the comparison model: baseline metadata, content hashes, three-way
  diff, or advisory-only heuristics

### 4. Drift Reporting With Next Actions

Status: partial

Current:

- `flow sync <target> --check` reports changed, stale, and conflicting files
- `flow doctor` reports sync state and drift status

Need:

- explain known drift causes
- distinguish source-changed updates, stale managed files, merge-protected
  runtime config, and unmanaged conflicts
- print the likely next command or manual action

Why it matters:

- existing-project adoption needs operator guidance beyond status labels
- clear drift output reduces edits to generated files and accidental deletion
  of runtime-local configuration

Next step:

- improve `--check` output before adding new adoption commands; it is already
  the first diagnostic surface

### 5. Project Override and Exclusion Model

Status: not started

Let a project opt out of generated surface area:

- do not generate this command
- do not generate this agent
- do not register this hook
- generate only selected runtime targets

Make exclusions visible in doctor and check output.

Why it matters:

- existing projects may not want the full framework surface
- explicit exclusions are safer than deleting generated files and rediscovering
  the same drift forever

Next step:

- define the manifest shape and precedence rules before implementation

### 6. Agent and Standards Review

Status: deferred from initial scaffold review

Review the role agents and standards against current flow behavior.

Focus on:

- whether each role prompt still matches how the role should work
- which standards are useful, too broad, duplicated, or stale
- `flow-define`, research behavior, review behavior, and cross-runtime wording

Why it matters:

- the command surface has matured faster than the full role and standard
  library
- real usage should decide which prompts stay detailed and which should be
  simpler

Next step:

- review agents and standards in small batches

## Deferred / Watch

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
