# flow-review

Use `flow-review` for structured review after implementation work.

<HARD-GATE>
Do NOT produce a verdict, findings, or the Review Summary until you have actually read both (a) the changed artifacts and (b) the original plan / requirements / acceptance criteria they are being judged against. Skimming is not reading. A verdict produced without comparison against intent is theatre — it provides false confidence and lets drift through. If either side is missing (e.g., no plan exists), say so explicitly in the Verdict rather than producing a judgment that pretends it has the comparison.
</HARD-GATE>

## Overview

This command judges the implementation against intent. It exists to separate "code was written" from "the slice is actually acceptable."

## When to Use

Use this command when:

- implementation is complete but acceptance is not yet clear
- a structured second pass is needed before archive
- a separate review lane owns correctness or acceptance

**When NOT to use:** initial shaping or planning work, or final memory packaging that belongs in `flow-archive`.

## Primary inputs

- implemented change
- relevant plan or requirements
- tests and validation evidence
- standards and project overlays that apply

## Primary outputs

- structured review verdict
- prioritized findings
- acceptance disposition
- residual-risk summary

## C-Lite Run Protocol

Review must enter and leave the lane through the CLI:

```bash
flow run transition <work-id> start-review
flow run transition <work-id> accept-review \
  --artifact review=.flow/runs/<work-id>/review.md
```

Do not produce an archive-ready acceptance claim until `accept-review`
succeeds. If review requests changes, do not advance the run to archive.

## Orchestration safety

Follow `standards/orchestration.md`. Reconcile claim provenance and provider identities, run `flow run validate-orchestration <work-id> --stage acceptance`, and require a verifier distinct from producer and evidence collector for high-risk work. Revision-2 `accept-review` rechecks it.

## Composition

Core roles (always invoked):

- `quality-reviewer` for correctness and structural-fit review
- `test-engineer` for coverage and proof review

Conditional roles (invoked when relevant):

- `security-reviewer` when the work touches sensitive or risky surfaces
- `ux-specialist` when user-facing fit is at stake
- `sre` when rollout, runtime, or observability fit is at stake

`flow-review` is the place where implementation is judged against intent, not just whether the work mechanically completes.

## Review Dimensions

Review should check:

1. requirement fit
2. UX or design-contract fit
3. technical fit
4. validation evidence
5. follow-up risks or gaps

## Review Workflow

**Every brief carries an evidence inventory** — what already exists in the area under review, with paths. Without it a reviewer cannot tell absent from unfound, and "X is missing" is an unsupported finding. See `standards/evidence.md`; `templates/adversarial-review.md` has the block.

1. Read the plan or requirements.
2. Read the implementation and changed tests.
3. Compare implementation to:
   - requested behavior
   - standards
   - acceptance criteria
4. Assess proof:
   - automated tests
   - manual checks
   - runtime evidence
5. Produce one of these dispositions:
   - ready to accept or archive
   - needs refinement
   - wrong slice or drifted scope

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

```md
## Review Summary

### Verdict
- Ready to accept/archive | Needs refinement | Wrong slice/drifted scope

### Findings
- Critical:
- Important:
- Suggestions:

### Requirement Fit
- [Assessment]

### Validation Fit
- [Assessment]

### Residual Risks
- [Assessment]
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "The tests pass, so review is done." | Passing tests are evidence, not the whole judgment. Scope, UX, architecture, and risk still matter. |
| "It's close enough; we can fix the rest later." | Unclear acceptance standards create drift and recurring rework. |
| "I already reviewed it while coding." | Self-review is useful but not a substitute for structured acceptance review. |
| "Only big issues matter." | Missing proof, wrong slice boundaries, and silent scope drift also matter. |

## Red Flags

- verdict produced without an explicit read of the original plan / acceptance criteria
- "the diff looks fine" as a verdict without comparison against intent
- no comparison to the original plan or acceptance criteria
- verdict is vague or non-committal
- missing distinction between critical issues and suggestions
- validation evidence is mentioned but not assessed
- review ignores UX, security, or runtime fit on relevant changes

## Verification

Before leaving `flow-review`, confirm:

- [ ] requirement fit was assessed explicitly
- [ ] validation evidence was assessed explicitly
- [ ] findings are prioritized
- [ ] the verdict is clear
- [ ] residual risks or next actions are stated

## Finish Criteria

`flow-review` is done when the team knows clearly whether to accept, refine, or rescope the work.
