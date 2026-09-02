# Test Shaping: Agent Web Access Policy

- Unit-test default, denial, re-enable, precedence, provenance, strict types,
  known names, duplicate keys, valid authorization, and rationale rules.
- Structurally test Claude normalization and Codex TOML mappings rather than
  relying on substring parity.
- Use fake-home integration tests to traverse the complete post-merge agent
  inventory, cover framework denial, overlay omission, explicit re-enable, and
  repeat-sync byte stability.
- For every invalid-policy family, seed an existing output and stale managed
  file, then prove both remain byte-identical after the rejected target sync.
- Preserve `manual_required` classifications in runtime smoke; configuration
  tests must not become claims of live provider or client behavior.
- Run focused tests, a targeted mutation check, the full suite, both adapter
  checks, doctor, static runtime smoke, candidate validation, and published
  release verification.
