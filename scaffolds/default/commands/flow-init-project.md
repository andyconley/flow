# flow-init-project

Walk the user through filling in `.flow/PROJECT.md` (and optionally project-specific overlays) with recommendations grounded in the current project state.

## Overview

After `flow setup project` scaffolds the overlay, the templates are bare placeholders. This command makes filling them in fast and grounded: read what's actually in the project (runtime context files, git history, file structure) and propose concrete content for each section. The user confirms or adjusts; you write the result back to `.flow/PROJECT.md`.

## When to Use

Use this command when:

- you just ran `flow setup project` and have a fresh empty overlay
- you want to revise an existing PROJECT.md based on how the project actually works now
- you want a guided walk through what to populate in the overlay

**When NOT to use:** for non-overlay work (use the workflow commands for that), or when PROJECT.md is already well-populated and only needs a minor edit (just edit the file directly).

## Primary inputs

- the existing `.flow/PROJECT.md` (template or current version)
- runtime-provided context files already in session context (for Claude Code, the CLAUDE.md hierarchy)
- `git log --oneline -30` plus `git log --stat -5` (recent activity, who is shipping)
- file structure of the project (presence of `catalog/`, `hackathon/`, `src/`, `tests/`, `docs/`, etc. to infer project type)
- relevant entries from the active runtime memory provider, when one exists

## Primary outputs

- a populated `.flow/PROJECT.md` written back to disk
- summary of what was inferred vs what required user input
- recommendation for next step (commit the overlay, run `/flow-boot` to verify)

## Composition

Core roles (always invoked):

- `business-analyst` for shaping role-provider declarations and project intent
- `tech-writer` for durable PROJECT.md wording

Conditional roles (invoked when relevant):

- `architect` if the project has substantial architecture (multiple Components/services/repos)
- `ux-specialist` if the project has a user-facing surface

## Workflow

1. **Verify scaffold present.** Confirm `.flow/PROJECT.md` exists. If not, recommend `flow setup project` first (shell command — offer to run it).
2. **Read project context.** Load the runtime-provided session context, sample recent git log (`--oneline -30` and `--stat -5`), list top-level files, and check the active runtime memory provider for relevant project entries. For Claude Code, that provider is auto-memory at `~/.claude/projects/<project-id>/memory/`; for Codex, no Flow-managed durable memory provider exists yet. This is the inference base for the proposals.
3. **Walk PROJECT.md section by section.** For each section:
   - Summary (name, type, primary runtime, short description) — propose based on inference; confirm with user.
   - Role providers (product owner, PM, requirements shaping, implementation, acceptance review) — for solo/personal projects propose "Andy" (or the actual git author) for all roles plus "+ Claude" where applicable; for team projects ask explicitly.
   - Collaboration deviations and tightening — propose based on project type; ask for confirmation.
   - Sources of truth — propose based on inference (issue tracker, ADR location, runtime context files, STATE.md, runtime memory provider).
   - Workflow notes — propose preferred small-change and gated-work paths based on observed work patterns.
   - Runtime and integration notes — propose based on file inspection (Dockerfile, package.json, requirements.txt, .github/workflows/, etc.).
4. **Write the updated `.flow/PROJECT.md`.** Edit the file in place — don't make the user copy-paste.
5. **Overlay check.** Run `flow project audit` and read the result to the user.
   - Runtime surfaces come from the user-level install (`flow setup user`) in every supported session. A project does not generate its own; project-level sync was retired.
   - Anything in the `identical` or `orphaned` buckets is a stale copy of a framework file, or a manifest entry naming a file that is gone. Recommend `flow project migrate` — dry run first — and offer to run it.
   - Anything in `differs` is either a real customization or a stale copy, and nothing local can tell which. Say that rather than guessing, and leave it alone.
6. **Optional follow-up.** Offer to also walk through the project's transient
   work state in `.flow/memory/STATE.md` — what is in flight, blocked, or
   pending right now. Do not offer to create project standards or project
   overlay files: an overlay holds no `standards/` or `project/` directory,
   and standards resolve from the user overlay and the framework default.
7. **Recommend next steps.** Commit the overlay change. Run `/flow-boot` to verify the overlay is being read correctly.

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

```md
## Project Overlay Initialization

### Project
- Name:
- Type:
- Short description:

### Sections written to `.flow/PROJECT.md`
- [Bulleted list of sections populated]

### Inferred vs asked
- Inferred (no user input needed): [sections]
- Asked the user: [sections]

### Overlay status
- [One of: "Clean — no framework copies, no stale declarations" | "{N} framework copies and/or stale declarations; recommend `flow project migrate`"]
- [Anything in `differs`, named, with the caveat that staleness and customization cannot be told apart locally]

### Follow-up offered
- [What you offered to do next — standards trim, project overlay population, etc.]

### File written
- `.flow/PROJECT.md` updated

### Recommended Next Command
- Commit the overlay change: `git add .flow/ && git commit -m "Initialize flow project overlay"`
- `/flow-boot` to verify the overlay is being read correctly
- (If the overlay is not clean): `flow project migrate` to review, then `--apply --yes` to act
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "PROJECT.md doesn't really matter; let it stay empty." | An empty PROJECT.md makes the overlay invisible to future sessions. The fields the user fills in are what make the overlay useful — without them, flow-boot can't surface project-specific role assignments or sources of truth. |
| "I can fill in everything from inference; no need to ask." | Role providers and acceptance criteria are *decisions*, not inferences. Default proposals are fine, but the user must confirm — they're the ones who own the project. |
| "Once written, PROJECT.md never needs revision." | As the project shape evolves, PROJECT.md should evolve with it. Re-running this command to refresh after a significant project change is the right move. |
| "Just write the proposal and skip the confirmation loop." | The whole point is a guided walk. Writing without confirmation defeats the purpose and produces a PROJECT.md the user didn't actually shape. |

## Red Flags

- PROJECT.md was written without user confirmation of role providers
- all sections came from inference (the user wasn't asked anything meaningful)
- "Andy" or `git config user.name` was guessed when the user wasn't asked
- inferred vs asked was not surfaced in the output
- the file was left with template placeholders ("Project name:" with nothing after it)

## Verification

Before leaving `flow-init-project`, confirm:

- [ ] `.flow/PROJECT.md` was actually written (not just proposed)
- [ ] role-provider fields are populated (not blank)
- [ ] inferred vs asked sections are distinguished in the output
- [ ] no template placeholders remain
- [ ] project-level sync status was explicitly stated ("not needed" vs "needed + offer to run")
- [ ] the user was given a clear next step (commit + flow-boot, plus sync if needed)

## Finish Criteria

`flow-init-project` is done when `.flow/PROJECT.md` is meaningfully populated for this project, the user has confirmed (not just inherited) the role-provider declarations, and they have a concrete next step.
