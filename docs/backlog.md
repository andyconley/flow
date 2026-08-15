# Backlog

## Purpose

This backlog tracks the work still needed before `flow` can be adopted confidently in two scenarios:

1. as a **personal workflow framework** installed at user level and used across every supported runtime session
2. as a **project-adoption framework** brought into existing repos with prior local conventions

The adoption bar is higher for existing repos because they already have:

- local workflow conventions
- existing AI runtime folders
- durable project docs
- prior state and migration history

## Adoption Readiness Themes

The remaining work clusters into six themes:

1. project migration safety
2. source-of-truth reconciliation
3. runtime adapter maturity
4. project upgrade ergonomics
5. operational confidence
6. project onboarding documentation

## Existing-Project Adoption Backlog

### 1. Existing `.claude/` import or reconciliation path

Status: not started

Need:

- a guided way to inspect an existing `.claude/` tree
- classify files as:
  - should become `.flow` source
  - should stay runtime-local and unmanaged
  - should be removed or replaced by generated output

Why it matters:

- Witmark already has meaningful `.claude/` history
- other existing repos are likely to as well
- manual reconciliation is error-prone and slows adoption

### 2. Existing-project migration playbook

Status: not started

Need:

- a documented step-by-step adoption path for existing repos
- explicit phases such as:
  - inventory
  - classify source-of-truth
  - scaffold `.flow`
  - port canonical materials
  - generate runtime adapters
  - validate no important behavior was lost

Why it matters:

- fresh-project bootstrap and existing-project adoption are different jobs

### 3. Content-aware refresh or upgrade support

Status: partial

Current:

- `flow refresh project` only adds missing files

Need:

- a way to detect when framework templates changed materially
- compare project files to newer template versions
- surface recommended merges without blindly overwriting local edits

Why it matters:

- existing projects will drift from the framework over time

### 4. Project-level manifest metadata for adoption state

Status: not started

Need:

- fields in `.flow/flow.toml` or another project manifest describing:
  - adoption phase
  - imported legacy runtime surfaces
  - known unmanaged runtime zones
  - migration exceptions

Why it matters:

- older projects need more explicit state than clean-slate projects

### 5. Runtime import tools beyond generation

Status: not started

Need:

- tools for importing or wrapping existing runtime assets
- examples:
  - import existing Claude skills into candidate `.flow/commands`
  - detect existing Claude agents that should become `.flow/agents`
  - identify overlapping generated and unmanaged runtime paths

Why it matters:

- generation alone is not enough for repos that already have runtime-specific content

### 6. Stronger drift reporting with recommendations

Status: partial

Current:

- `--check` reports stale or updated files

Need:

- drift output that explains:
  - generated file changed because source changed
  - unmanaged conflict detected
  - stale managed file should be removed
  - likely next command to run

Why it matters:

- existing-project adoption needs clearer operator guidance than greenfield setup

### 7. Runtime-specific agent strategy for non-Claude targets

Status: completed for Codex, open for future runtimes

Current:

- Claude gets generated agents
- Codex gets generated native agents

Need:

- decide whether future runtimes should:
  - receive generated agents
  - receive adapted role prompts
  - stay command-skill-only

Why it matters:

- adoption in another existing repo may depend on a different runtime surface than Witmark

### 8. Project-level override and exclusion model

Status: not started

Need:

- a clean way for a project to say:
  - do not generate this command
  - do not generate this agent
  - use this runtime target only
  - exclude this hook

Why it matters:

- existing projects may not want the full framework surface

### 9. Safer settings merge policy

Status: partial

Current:

- Claude settings support managed hook merging

Need:

- finer-grained ownership metadata
- safer behavior if settings shape changes
- a clearer policy for future runtime-level config merges

Why it matters:

- settings files in existing repos are likely to already contain important local customizations

### 10. Adoption verification checklist

Status: not started

Need:

- a checklist for proving adoption is safe:
  - `.flow` contains the real source of truth
  - generated runtime files match expected surfaces
  - unmanaged files are preserved intentionally
  - collaborators know where to edit
  - help and docs reflect the adopted runtime model

Why it matters:

- without a checklist, adoption success becomes subjective

## Witmark-Specific Adoption Work

These are the extra items needed for Witmark specifically.

### A. Reconcile current `.claude` canonical materials

Need:

- decide what remains canonical in:
  - `.claude/STATE.md`
  - `.claude/DECISIONS.md`
  - `.claude/rlm/...`
- port what belongs in `.flow`
- leave only runtime-local outputs in `.claude`

### B. Preserve Witmark platform/project specifics in project overlays

Need:

- keep Forge, Jira, terminology, UX, and domain specifics in Witmark project-level `.flow` docs
- avoid re-generalizing them back into framework standards

### C. Migrate Witmark command and agent usage without losing behavior

Need:

- compare current Witmark runtime behavior with generated `flow` behavior
- confirm no collaboration or review pattern was lost during source-of-truth migration

## Another Existing Project Adoption Work

For a second existing project, the likely additional backlog is:

### A. Runtime inventory

Need:

- identify whether the project already uses Claude, Codex, both, or neither

### B. Source inventory

Need:

- identify existing standards, workflows, prompts, templates, and operator docs that should map into `.flow`

### C. Minimal runtime target choice

Need:

- choose the smallest runtime adapter surface needed for first adoption

Why it matters:

- starting with the smallest viable runtime surface lowers migration risk

## Recommended Order

Before broad existing-project adoption, the strongest sequence is:

1. write the existing-project adoption playbook
2. add `.claude/` reconciliation/import tooling
3. add content-aware project upgrade support
4. deepen drift reporting and migration guidance
5. define project-level overrides and exclusions
6. validate the process end-to-end in Witmark
7. validate it again in a second existing repo with different runtime conditions

## Personal-Framework Use Case Backlog

These items are specific to the user-level install model — using flow as a personal framework rather than adopting it into a specific project.

### P1. CLI implementation of stacked overlay traversal

Status: prose contract only

Current:

- Command contracts describe how stacked overlays merge (most-specific overrides; reads merge across levels; writes go to most-specific)
- The CLI itself does not walk ancestor directories or merge `.flow/` overlays

Need:

- CLI helpers that walk up from cwd, find ancestor projects with `.flow/`, and merge their overlays
- A consistent merge model that flow-boot, flow-status, flow-resume, and flow-archive can rely on
- Tests for stacked overlay scenarios (nested projects with conflicting PROJECT.md, runs at multiple levels, etc.)

Why it matters:

- Today the stacked-overlay behavior depends on Claude doing what the prose contract asks; a CLI implementation makes it deterministic and testable

### P3. Agents and standards review pass

Status: deferred from initial scaffold review

Current:

- 8 commands and 1 agent (`quality-reviewer`) were reviewed and customized in the initial scaffold-customization pass
- 11 other agents and all 23 standards have only been inspected, not reviewed against personal working preferences

Need:

- A focused review pass per agent: does the prompt reflect how this role should engage with Claude?
- A focused review pass per standard: does it apply to actual working surfaces, or is it over-spec?
- Decisions about which agents to keep, drop, or rename

Why it matters:

- Today the agents and standards inherit content from the develop-branch codex-hardening work, not from distilled personal conventions
- Deferred intentionally until real usage surfaces what's actually wrong vs what just reads oddly on paper

### P7. Engagement-discipline pattern duplication

Status: pattern shipped (v0.4.1), abstraction deferred

Current:

- `<HARD-GATE>` blocks + three-phase structure (Engagement → Shaping/Solutioning → Capture) are duplicated across `flow-solution.md`, `flow-plan.md`, `flow-implement.md` (Phase 1 only), `flow-review.md`, and `solution-architect.md`
- Each command's anti-pattern section and red flags carry parallel content adapted to that command's specifics

Need:

- Consider promoting the engagement-discipline pattern to `standards/engagement-discipline.md` that the commands cite by section name, rather than duplicating the structure inline
- Citations would follow the existing pattern (commands already cite `standards/git-commits.md`, `architecture.md`, etc.)

Why deferred:

- Abstraction at 4 occurrences is borderline; at 5 it would be justified
- Premature abstraction is worse than the current duplication — each command's framing is slightly different and the pattern is still settling
- Revisit when a fifth command needs the same discipline, or when one of the existing four needs a non-trivial pattern update that would otherwise require editing the same content in multiple places
