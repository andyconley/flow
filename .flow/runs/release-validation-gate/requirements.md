# Requirements: Automated Release Validation Gate

## Problem

Flow's `main` workflow currently gives semantic-release write permission and invokes publication before running the deterministic checks used to validate v0.21.0. A future release can therefore create a tag, GitHub release, and changelog commit before the candidate has passed the full test suite, generated-help consistency, release staging, isolated installation, upgrade, doctor, sync, and runtime-smoke checks.

## Users

- Flow users need published tags to represent candidates that passed the deterministic release checks.
- Flow maintainers need a repeatable release decision that does not depend on a remembered manual checklist.
- Support and release owners need evidence tied to the exact source SHA and proposed version.

## Approved requirements

1. Analyze the exact pushed `main` SHA before any remote write and determine whether a semantic release is required.
2. A non-release commit must finish successfully without running the expensive candidate gate or invoking publication.
3. A release-producing commit must pass every deterministic candidate check before any tag, GitHub release, or changelog release commit is created.
4. The analysis step must not receive credentials capable of writing to GitHub. Semantic-release policy remains the source of version and release-note decisions; preview logic must not reimplement those rules independently.
5. Candidate validation must exercise the exact analyzed SHA and predicted version through a temporary local release representation, including both fresh installation and upgrade from the previous release.
6. Publication must fail closed when the branch tip, previous release identity, predicted version, notes, plan, or evidence differs from what was validated.
7. Publication has no manual bypass, `continue-on-error`, force-push, or retry mode that skips a failed gate. The recovery path is a new corrective commit.
8. After publication, verify the public tag, generated release commit, changelog, GitHub release, non-empty notes, fresh tagged installation, and tagged upgrade path.
9. Post-publication failure must be reported accurately as a published-release failure and handled by repair forward; it cannot be described as prevented publication.
10. Live Claude/Codex discovery, applied model and effort routing, external identity, and actual capability grants remain explicit manual limitations.
11. Release evidence must be structured, versioned, retained as workflow artifacts, and bound to the exact workflow, SHA, version, and check outcomes.
12. The existing versioning rules and unrelated pull-request policy remain unchanged.

## Constraints

- Preserve semantic-release `25.0.9` and the pinned plugin versions unless implementation evidence requires a separately approved change.
- Keep release-rule and note-rendering policy shared between preview and publication.
- Do not parse semantic-release console prose as an API.
- Pass release notes and artifact values through files, validated action outputs, or environment variables rather than executable shell interpolation.
- Keep the canonical checkout's unrelated `docs/backlog.md` edit outside this work.

