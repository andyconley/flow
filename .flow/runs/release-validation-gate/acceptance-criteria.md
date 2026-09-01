# Acceptance Criteria: Automated Release Validation Gate

1. A release-producing commit cannot invoke write-capable semantic-release publication until all deterministic candidate checks have passed.
2. Analysis runs against the exact pushed SHA without a GitHub write credential and emits a validated, versioned release plan.
3. A non-release commit exits successfully, publishes nothing, and skips candidate and post-publication validation.
4. The candidate gate runs the full Python suite, generated-help check, clean-tree check, release staging/import validation, candidate fresh install, candidate upgrade, setup, Claude and Codex sync checks, `doctor --check`, static runtime smoke, and representative changed CLI behavior.
5. Candidate installation and upgrade use a temporary local repository whose candidate tag resolves to the analyzed SHA and predicted version; no production tag is created.
6. Each induced candidate-gate failure prevents publisher invocation and leaves the remote tag, GitHub release, and changelog release state unchanged.
7. Publication rejects stale branch or tag state, plan/evidence digest mismatch, or disagreement between the original and repeated release analysis.
8. The published tag's relationship to the validated SHA is proven while allowing only the expected semantic-release changelog commit created by `@semantic-release/git`.
9. Post-publication verification checks the tag, release commit, changelog entry, GitHub release, non-empty notes, public fresh installation, and public upgrade path.
10. Post-publication failure leaves the workflow red with repair-forward guidance and never deletes or rewrites the published release.
11. Workflow permissions default to read-only; only the publication job receives the minimum write permissions and token, after validation succeeds.
12. Workflow ordering, conditions, permissions, no-release behavior, identity propagation, failure/no-write behavior, and structured contracts have automated tests that do not publish a real release.
13. Maintainer documentation distinguishes pre-publication blockers, post-publication checks, and manual live-client checks.
14. Existing semantic version rules and release-note rendering remain behaviorally unchanged.

