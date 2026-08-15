# Backlog

## Purpose

This backlog tracks remaining work that would make `flow` easier to adopt,
maintain, and trust across supported runtime sessions.

Keep this file focused on open work. Completed release history belongs in
`CHANGELOG.md`. Project-specific migration notes belong in that project's own
overlay or in a dedicated adoption case study, not in the general flow backlog.

## Current Priorities

### 1. Existing-Project Adoption Playbook

Status: not started

Need:

- document the step-by-step path for adopting flow in a repo that already has
  local workflow conventions, runtime folders, and project memory
- cover inventory, source-of-truth classification, `.flow` scaffolding,
  migration of canonical materials, adapter generation, and validation
- include when to use a structured chat summary versus a durable migration
  artifact

Why it matters:

- fresh-project setup and existing-project adoption are different jobs
- without a playbook, every adoption depends on the current agent remembering
  the right sequence

Next step:

- write `docs/adoption-playbook.md` for existing projects, then link it from
  README and this backlog

### 2. Runtime Surface Inventory and Reconciliation

Status: not started

Need:

- inspect existing runtime surfaces before flow generates over or beside them
- classify files across `.claude/`, `.agents/skills/`, and `.codex/` as:
  - should become `.flow` source
  - should stay runtime-local and unmanaged
  - should be replaced by generated flow output
  - should be removed after migration
- detect overlaps between generated flow paths and existing unmanaged files

Why it matters:

- generation alone is not enough for repos that already have runtime-specific
  content
- a runtime-neutral inventory keeps adoption from being Claude-shaped by
  accident

Next step:

- start with a read-only `flow adopt inventory` or equivalent report; defer
  writes/imports until the classification output is useful

### 3. Content-Aware Project Refresh

Status: partial

Current:

- `flow refresh project` only copies missing scaffold files

Need:

- detect when framework templates changed materially after a project copied
  them
- compare project files to newer template versions without overwriting local
  edits
- surface recommended merges, conflicts, or "leave local" decisions

Why it matters:

- project overlays will drift from the framework over time
- missing-file refresh is safe but not enough once copied files have evolved

Next step:

- define the comparison model first: baseline metadata, content hashes,
  three-way diff, or advisory-only heuristics

### 4. Drift Reporting With Next Actions

Status: partial

Current:

- `flow sync <target> --check` reports changed, stale, and conflicting files
- `flow doctor` reports sync state and drift status

Need:

- explain why drift exists where flow can know it
- distinguish source-changed updates, stale managed files, merge-protected
  runtime config, and unmanaged conflicts
- print the likely next command or manual action

Why it matters:

- existing-project adoption needs operator guidance, not just red/green state
- clearer drift output reduces the chance that someone edits generated files
  or deletes runtime-local configuration

Next step:

- improve `--check` output before adding new adoption commands; it is already
  the user's first diagnostic surface

### 5. Project Override and Exclusion Model

Status: not started

Need:

- let a project explicitly opt out of generated surface area, such as:
  - do not generate this command
  - do not generate this agent
  - do not register this hook
  - generate only selected runtime targets
- make exclusions visible in doctor/check output

Why it matters:

- existing projects may not want the full framework surface
- explicit exclusions are safer than deleting generated files and letting drift
  reports rediscover them forever

Next step:

- define the manifest shape and precedence rules before implementation

### 6. Adoption Verification Checklist

Status: not started

Need:

- define how an adopter proves the migration is complete:
  - `.flow` contains the real source of truth
  - generated runtime files match expected surfaces
  - unmanaged files are intentionally preserved
  - collaborators know where to edit
  - README/help/docs reflect the adopted runtime model
- include this checklist in the adoption playbook

Why it matters:

- adoption should end with evidence, not a vague sense that the files look
  right

Next step:

- draft the checklist as part of `docs/adoption-playbook.md`

### 7. Agent and Standards Review

Status: deferred from initial scaffold review

Need:

- review each role agent against current flow behavior and personal working
  preferences
- review standards for practical usefulness: keep, simplify, merge, or remove
- pay special attention to `flow-define`, research behavior, review behavior,
  and cross-runtime wording

Why it matters:

- the command surface has matured faster than the full role/standard library
- real usage should shape which prompts stay heavy and which can be simpler

Next step:

- review agents and standards in small batches rather than trying to redesign
  the whole library at once

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

- a concrete workflow needs the CLI, rather than the command contracts, to own
  stacked overlay resolution

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
