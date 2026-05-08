# flow-archive

Use `flow-archive` to close out a completed slice or run and convert short-lived execution into durable project memory.

## Overview

This command closes the loop on completed work. It captures what changed, what was proven, what remains risky, and what the project should remember going forward.

## When to Use

Use this command when:

- implementation and review are complete
- validation is complete enough to close the work
- a run needs a final summary, residual-risk note, and memory update

Do not use this command to decide whether work is ready. Use `flow-review` first when acceptance is still uncertain.

**When NOT to use:** before review is complete, or when the work is still actively being refined.

## Primary inputs

- the completed run or slice artifacts
- review findings and resolution status
- validation evidence
- current durable memory:
  - `.flow/memory/STATE.md`
  - `.flow/memory/DECISIONS.md`

## Primary outputs

- completion summary
- validation summary
- residual-risk and follow-up summary
- durable memory updates
- run completion marker

## Composition

Primary roles:

- `tech-writer` for durable summary and memory wording
- `code-reviewer` when unresolved review debt needs to be summarized accurately
- `support-lead` when known operational caveats or workarounds should be preserved

The archive command does not replace review. It packages the accepted outcome.

## Archive Workflow

1. Identify the run or slice being closed.
2. Summarize what changed.
3. Record validation status:
   - tests run
   - manual checks
   - runtime or deploy checks
4. Record residual risks, follow-ups, and deferred work.
5. Update `.flow/memory/STATE.md` and `.flow/memory/DECISIONS.md` if the work changed durable project knowledge.
6. Mark the run complete.

## Output Format

```md
## Archive Summary

### Work Closed
- [Run or slice]
- [What changed]

### Validation
- Automated:
- Manual:
- Runtime/deploy:

### Residual Risks
- [Known caveats]

### Follow-up Work
- [Deferred or future work]

### Memory Updates
- STATE:
- DECISIONS:
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "The code is merged, so archive is unnecessary." | Merge is not memory. Archive is what makes the outcome durable. |
| "Residual risks are obvious from the diff." | Risks disappear quickly unless they are written down explicitly. |
| "We can update STATE and DECISIONS later." | Later is usually never; archive is the right time to make memory durable. |

## Red Flags

- no explicit validation status
- memory updates omitted
- follow-up work implied but not listed
- archive summary is just a changelog dump

## Verification

Before leaving `flow-archive`, confirm:

- [ ] what changed is summarized clearly
- [ ] validation status is explicit
- [ ] residual risks and follow-up work are explicit
- [ ] durable memory was updated where needed
- [ ] the run is clearly marked complete

## Finish Criteria

`flow-archive` is done when:

- the closed work is summarized clearly
- validation status is explicit
- durable memory reflects the new reality
- remaining risks are recorded rather than implied
