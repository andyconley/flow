# Handoff: v8-live-validation

- **Status:** ready for review. The outcome is that the validation found Flow defects (R7): a valid result, but not a completed job.

## What happened

The first live v8 chartered job ran through sealed authority, the Claude manager (3 calls), and a Flow-granted Claude edit. The edit worker then aborted on its 1 MiB event-log cap (D1), so Flow marked the edit `unknown`. The attempt was abandoned by releasing the lead claim. Separately, the help generator emits raw `|` in table cells, which breaks Markdown and would have failed the job's sync test (D2).

## Evidence

- `validation-results.md`, and the `evidence/` folder: preflight, baseline, launch output, inspect snapshots, the worktree diff and the release.

## Next actions

1. **A fix run.** D1: split the edit worker's read cap from its log cap, parse the stream line by line, fix the trace abort too, and test a stream over 1 MiB. D2: escape pipes in the help generator.
2. **`v8-live-validation-2`,** which reuses the definition and runbook. The job test and baseline must be redone for escaped pipes.
3. **Framework gaps to record at archive:**
   - there is no CLI for lead release or supersede;
   - the job charter isn't covered by sealed digests;
   - manifest `timeout_seconds` values are ignored for the Ollama verifier;
   - an uncertain send leaves a validation run with no path to a second attempt.

## Worktree

`~/src/flow-v8-live-job` still holds the partial producer edit, which is also saved as `evidence/attempt-1-worktree.diff`. It is safe to remove once the next run creates its own.
