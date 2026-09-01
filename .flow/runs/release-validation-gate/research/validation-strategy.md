# Validation Strategy Analysis

Keep the workflow thin and place decision normalization, schema validation, identity comparison, candidate execution, and post-publication verification behind testable repository helpers. Use fixtures and local bare Git repositories to prove release/no-release decisions, failure/no-write behavior, candidate fresh install, candidate upgrade, stale-plan refusal, and tag ancestry without a real publication token.

Static workflow tests must assert job order, conditions, permissions, exact-SHA checkout, absence of bypasses, and publication dependency on passed evidence. Public-artifact checks remain explicitly post-publication.

