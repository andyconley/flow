# Findings Reconciliation

## Accepted

- Automate the release gate before addressing live client discovery.
- Deterministic checks block publication; public-tag and live-client checks remain post-publication.
- Determine release intent before the expensive gate and before any remote write.
- Use exact-SHA/version evidence and fail closed on drift.
- Keep publication bypass-free and repair forward after any published failure.
- Use structured results and versioned JSON contracts rather than parsing console prose.
- Give write permissions only to the publication job.

## Rejected

- Giving the analysis job live repository write credentials merely because semantic-release dry-run verifies push permission.
- Running the full candidate gate for commits that cannot produce a release.
- Treating public-tag checks as pre-publication proof.
- Deleting tags, releases, or history after a partial or failed publication.

## Deferred

- Live Claude/Codex discovery and applied model/effort verification remain under `runtime-smoke-cannot-exercise-client-discovery`.

## Open conflicts

- None.

