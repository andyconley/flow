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
- current transient work state: `.flow/memory/STATE.md` (every stacked overlay level)
- current durable project memory in the active runtime provider, when one exists

## Primary outputs

- completion summary
- validation summary
- residual-risk and follow-up summary
- durable memory updates
- run completion marker

## C-Lite Run Protocol

Archive closes the run through the CLI:

```bash
flow run transition <work-id> archive \
  --disposition capability_gaps=<recorded|n/a> \
  --disposition memory=<updated|n/a>
```

For scout work that never escalated into the gated core path, create only the
minimal closure envelope:

```bash
flow run transition <work-id> archive-scout \
  --artifact scout_summary=.flow/runs/<work-id>/scout-summary.md \
  --disposition capability_gaps=<recorded|n/a> \
  --disposition memory=<updated|n/a>
```

Do not mark archive complete until the transition succeeds.

## Composition

Primary roles:

- `tech-writer` for durable summary and memory wording
- `quality-reviewer` when unresolved review debt needs to be summarized accurately
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
5. **Record capability gaps observed during the run** — what the *framework* was missing, as distinct from what the work left undone. Look for: steps you carried out by hand that a command or skill should have done, a standard whose absence caused rework, an agent role that would have fit and does not exist, and artifacts you wanted a template for. This is the only point in the phase machine where the run is fresh enough to notice and finished enough to judge. If nothing was missing, say so explicitly — an omitted section reads as "not considered."

   **Read the ledger before you write to it.** Run `flow gaps list` and compare what you observed against the existing keys. Reuse a key when the gap is the same gap — that reuse is the only thing that makes a repeat countable, and a new key for an old problem silently starts a second lineage. Then record each gap:

   ```
   flow gaps add --key <slug> --summary "<what was missing>" --project <project> --run <work-id>
   ```

   **Write the summary about the framework, never about the work.** The ledger is committed and pushed, and a promoted entry goes into the flow repository, which does not share the ledger's audience. Say what flow was missing — "no template for symptom-first operational docs" — not what the run contained. No customer or client names, no internal system or project codenames, no quoted file content, error text, identifiers, paths, or anything pasted from configuration. A gap is a statement about the framework and stays useful without any of that.

   **Tell the engineer when a gap is a repeat**, and say how many times it has now been seen. A gap recurring after it was already noticed is a different fact from a gap seen once, and it is the fact worth acting on. Offer to promote it into the backlog with `flow gaps promote --key <slug>` — and do not run that until they say yes. Promotion writes a file; committing and pushing it are separate decisions that are theirs alone, so ask for those separately and never do them as a side effect.

   If `flow` is unavailable, record the gaps in the output section as before and say the ledger was not updated.
6. **Update transient work state** in `.flow/memory/STATE.md` at the **most-specific stacked overlay** (e.g., when archiving in path-nexus, writes go to `~/KB/repos/path-nexus/.flow/memory/STATE.md`, not the workspace's). STATE.md should reflect what is now in flight, blocked, or pending — not durable facts.
7. **Record durable decisions in the active runtime memory provider when one exists.** For Claude Code, write auto-memory at `~/.claude/projects/<project-id>/memory/`: for each cross-cutting decision worth remembering across sessions, write a structured memory file with frontmatter (`type: project`) and add a one-line entry to `MEMORY.md`. For Codex, no Flow-managed durable memory provider exists yet; report "n/a — no durable provider" rather than inventing a path. Do NOT write durable decisions to `.flow/memory/`; that file is transient state only.
8. If the work materially affects a parent overlay's state, surface that in the archive output so it can be picked up in a separate parent-level archive.
9. Mark the run complete.

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

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

### Capability Gaps Observed
(always present; what the framework was missing, or "none observed")
- [Step carried out by hand that a command or skill should own]
- [Standard whose absence caused rework]
- [Agent role that would have fit and does not exist]
- [Artifact that wanted a template]
- Ledger: (always present; the key recorded for each gap and whether it was new or a reuse, or "not updated" and why)
- Repeats: (always present; any key now seen more than once, with its count, or "none")

### Memory Updates
- STATE (`.flow/memory/STATE.md`): (always present; describe the transient work-state change, or "n/a — work state unchanged")
- Runtime memory entries written: (always present; list new or updated provider files by name + one-line summary, or "n/a — no durable decisions recorded/provider unavailable")
- Parent-overlay implications: (only if changes here affect a higher overlay)
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "The code is merged, so archive is unnecessary." | Merge is not memory. Archive is what makes the outcome durable. |
| "Residual risks are obvious from the diff." | Risks disappear quickly unless they are written down explicitly. |
| "We can update STATE and runtime memory later." | Later is usually never; archive is the right time to make memory durable when a provider exists. |
| "STATE.md and runtime memory hold the same kind of thing." | They do not — STATE.md is transient work state at the project; runtime memory holds durable cross-session facts and decisions. Mixing them defeats both. |
| "Nothing was missing from the framework, so I'll skip that section." | Write "none observed." An omitted section is indistinguishable from one that was never considered, and the gap notes are only useful as a corpus — a run that silently skips them removes a data point rather than adding a null one. |

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
- [ ] capability gaps are recorded (or explicitly marked "none observed")
- [ ] the ledger was read before it was written, and existing keys were reused where the gap was the same gap
- [ ] each gap was appended with `flow gaps add` (or the ledger was explicitly reported as not updated)
- [ ] any repeat was surfaced to the engineer with its count, and promotion was offered rather than performed
- [ ] nothing was committed or pushed without being asked for separately
- [ ] STATE.md was updated (or explicitly marked "n/a")
- [ ] durable decisions were written to the active runtime memory provider (or explicitly marked "n/a — no durable decisions recorded/provider unavailable")
- [ ] writes went to the most-specific overlay; parent-overlay implications surfaced if applicable
- [ ] the run is clearly marked complete

## Finish Criteria

`flow-archive` is done when:

- the closed work is summarized clearly
- validation status is explicit
- durable memory reflects the new reality
- remaining risks are recorded rather than implied
