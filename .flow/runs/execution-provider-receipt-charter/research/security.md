# Security role review

Evidence inventory: `scaffolds/default/standards/orchestration.md`, `cli/orchestration.py`, `docs/adr/0001-separate-orchestration-contracts.md`, and the draft requirements/acceptance criteria.

High finding: A worker could fabricate or alter its own success receipt. Disposition: require coordinator/provider-side observation outside worker write scope; bind approved inputs, baseline, terminal result, commit, observed delta, and validation. Worker prose remains a claim. Add tampered/worker-only receipt refusal to acceptance.

Medium finding: Declared changed paths could omit uncommitted, untracked, symlink, or out-of-scope changes. Disposition: require complete observed baseline-to-result scope comparison and block unexplained delta.

Medium finding: Secrets can leak through commands, environment, paths, validation, commit metadata, and failure diagnostics, beyond stdout/stderr. Disposition: exclude sensitive values from durable receipts and referenced evidence by default, with bounded access-controlled references and sanitized summaries.
