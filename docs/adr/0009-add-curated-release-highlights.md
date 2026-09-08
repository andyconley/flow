# ADR 0009: Add curated release highlights inside semantic-release

- Status: accepted
- Date: 2026-09-07
- Related decision: [ADR 0002](0002-gate-semantic-release-publication.md)

## Context

Flow's generated changelog and GitHub release notes list Conventional Commit
subjects. Those subjects are useful change records, but a capability delivered
over several commits can remain hard to identify. Archive retrieval exposed the
problem: its public release listed implementation commits without stating the
resulting workflow behavior.

Release notes are part of the exact-SHA publication contract in ADR 0002. A
workflow step that rewrites notes after semantic-release analysis would bypass
the plan digest and repeated-analysis comparison.

## Decision

A release-impacting commit may carry one optional `Release-Note: <text>` trailer.
The value is a single line of 1-240 UTF-8 bytes, contains no control or
bidirectional-formatting characters or HTML comment delimiters, and does not
start with a Markdown heading. Multiple release commits retain
semantic-release's commit order; identical values are not deduplicated.

`scripts/release-highlights.cjs` is a local semantic-release `generateNotes`
plugin. It renders accepted trailers as `### Highlights` and runs immediately
before `@semantic-release/release-notes-generator`. With no trailers it returns
an empty string. Malformed trailers fail note generation before publication.

Preview and publish import the same plugin list from the selected source SHA.
The combined notes flow unchanged into the release plan, notes digest,
candidate evidence, repeated analysis, publication, and public readback. The
plugin does not classify commits or change version selection.

ADR 0008 was already allocated to expertise serialization before this decision
was implemented, so this record uses the next available number.

## Consequences

- Maintainers can add one concise, reader-facing outcome without hand-editing a
  generated release.
- Commit subjects and standard generated sections remain the complete change
  inventory.
- A malformed `Release-Note` blocks the release path rather than silently
  dropping or repairing input.
- The local plugin contract is versioned in the release-policy identity. Any
  parser or rendering change must update that identity and its tests.

## Alternatives considered

- Post-process generated notes in the workflow: rejected because it would
  create a second, weakly bound release-note path.
- Use commit subjects alone: retained as the default, but insufficient for
  capabilities delivered through several technical commits.
- Require a highlight on every release: rejected because small releases often
  need only the generated change list.
