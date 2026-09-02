# Findings Reconciliation

## Accepted

- Automate the release gate before addressing live client discovery.
- Deterministic checks block publication; public-tag and live-client checks remain post-publication.
- Determine release intent before the expensive gate and before any remote write.
- Use exact-SHA/version evidence and fail closed on drift.
- Keep publication bypass-free and repair forward after any published failure.
- Use structured results and versioned JSON contracts rather than parsing console prose.
- Give write permissions only to the publication job.
- Isolate the full candidate suite from the runner home while binding
  `~/.flow/source` to the exact checked-out source.
- Preserve the canonical GitHub HTTPS URL explicitly during credential-free
  preview so release-note links are stable without relying on an ignored API
  alias.

## Rejected

- Giving the analysis job live repository write credentials merely because semantic-release dry-run verifies push permission.
- Running the full candidate gate for commits that cannot produce a release.
- Treating public-tag checks as pre-publication proof.
- Deleting tags, releases, or history after a partial or failed publication.

## Deferred

- Live Claude/Codex discovery and applied model/effort verification remain under `runtime-smoke-cannot-exercise-client-discovery`.
- Node 20 deprecation warnings emitted by pinned artifact actions are a
  non-blocking dependency-maintenance follow-up; they did not affect this
  release's validation or publication result.

## Resolved during hosted validation

- Run `33564014091` exposed an ignored semantic-release API alias. The preview
  now receives a validated canonical repository URL through explicit process
  state. The next analysis passed and the failed run made no write.
- Run `33565098215` exposed runner-home coupling in the full suite. Candidate
  validation now uses an isolated home, removes inherited Git credentials, and
  binds Flow source to the exact checkout. The final candidate passed 770 tests
  and the failed run made no write.
- Independent security, quality, test, and operational reviews have no blocking
  finding. Hosted run `33632240778` supplied the previously pending public
  publication and readback proof.

## Open conflicts

- None.
