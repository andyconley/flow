# Architecture Analysis

Use four dependent jobs: `analyze`, `validate-candidate`, `publish`, and `verify-published`. The first three operate on one immutable source identity carried through a versioned release plan and evidence digest. Publication repeats analysis and rejects drift before receiving permission to write.

Use semantic-release's structured result through a thin repository helper or Action boundary; do not scrape logs or reproduce the release algorithm. Because semantic-release dry-run verifies push permission, analysis should target a local mirror and omit live publication plugins while importing the same analyzer and notes policy. Only publication receives GitHub write permissions.

`@semantic-release/git` may tag a generated changelog commit rather than the original source SHA. Verification must prove the expected ancestry and allowed generated diff instead of assuming tag equality with the pushed SHA.
