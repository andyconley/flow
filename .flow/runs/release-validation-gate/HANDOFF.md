# Handback: Automated Release Validation Gate

## Status

Implementation is complete and the first full release is shipped. Flow
`v0.22.0` was published by hosted workflow run
[`33632240778`](https://github.com/andyconley/flow/actions/runs/33632240778) and
publicly verified successfully.

## What shipped

The release path is now a serialized, fail-closed sequence:

`analyze -> validate-candidate -> publish -> verify-published`

The candidate gate validates the exact analyzed SHA, predicted version, release
notes, full test suite, installation and upgrade paths, setup, sync, doctor,
runtime smoke, and representative CLI behavior. Evidence is structured,
digest-bound, retained, and checked before the sole write-capable publication
job. Failures do not delete or rewrite remote state; the documented recovery is
a corrective commit and a new run.

## Shipped release proof

- Validated source: `e05178b78420db53c3f7431448e1d188cc958441`
- Published version/tag: `v0.22.0`
- Generated release commit: `f5f45565c64f881f9ba07c85d23fb95e90cb292b`
- Generated commit parent: `e05178b78420db53c3f7431448e1d188cc958441`
- Generated commit contents: `CHANGELOG.md` only
- GitHub release: [`v0.22.0`](https://github.com/andyconley/flow/releases/tag/v0.22.0)
- Candidate checks: 13/13 passed; full suite: 770 tests passed
- Public verification: 11/11 checks passed, including fresh install and upgrade
- Expected shared-state delta: fully satisfied; no unexpected delta

The retained authorization and publication chain is under `release/`: hosted
plan and evidence/logs, both pre-publication baselines, publication result,
public readback, and expected-versus-observed comparison. Plan, evidence, and
notes digests are recorded in those artifacts and in the review files.

## Fail-closed evidence

Two earlier hosted attempts demonstrate the stop-before-write behavior:

- Run `33564014091` stopped during read-only analysis because preview URL state
  was not preserved; no publication occurred.
- Run `33565098215` stopped during candidate validation because the full suite
  was coupled to the runner home; publication and verification were skipped.

Both issues were repaired forward. The successful run exercised the repaired
boundaries without weakening the gate.

## Remaining limitation

The non-interactive hosted runner cannot prove live Claude/Codex client
discovery, applied model/effort routing, external identity, or actual client
capability grants. Static generated surfaces and sync checks passed. This is a
documented manual smoke-check boundary, not a release failure and not a claim
that interactive behavior was validated.

## Resume and repair-forward actions

If a future run fails before publication, preserve its artifacts, inspect the
named contract failure and retained log, make a corrective commit, and rerun
the gate. If publication may have partially occurred, use the read-only
reconciliation path and public readback to classify observed state. Preserve
any published tag/release/history; do not force-push, delete, or blind-retry.
For a post-publication verification failure, report it as a published-release
failure and repair forward with a corrective commit.

Operational guidance is canonical in `docs/release-runbook.md`.

## Next lifecycle step

Run `$flow-review` for final acceptance of this implementation, then
`$flow-archive` to close the run and preserve its durable memory. The next
maintainer should treat the hosted public verification artifact as the
authoritative proof for the shipped release and the interactive client check
as the only explicitly unexercised boundary.
