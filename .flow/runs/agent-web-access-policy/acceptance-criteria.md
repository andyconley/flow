# Acceptance Criteria: Global Flow Agent Web Access Policy

## Policy resolution

- [ ] One canonical default enables semantic `web_research` for every manifest
  agent, including agents added later.
- [ ] An explicit per-agent disable with a non-empty rationale overrides the
  default after framework/user-overlay merge.
- [ ] Invalid values, missing rationale, or an ambiguous replacement of a
  protected opt-out fail closed before adapter output is written.

## Runtime adapters

- [ ] Every enabled Claude agent has exactly one `WebSearch` and one `WebFetch`
  declaration without losing its other tools.
- [ ] Every enabled Codex agent has an explicit documented native web-search
  configuration capable of current external retrieval.
- [ ] Disabled Claude agents have neither web tool; disabled Codex agents carry
  an explicit native disable rather than relying on omission.
- [ ] Both adapters receive the same effective policy and behavioral guidance.

## Behavioral and security guidance

- [ ] Web use requires a named external/current research question explicitly
  marked as required in the user task or orchestrator brief.
- [ ] Merely selecting a role or entering a Flow workflow does not authorize web
  use.
- [ ] Shared instructions treat retrieved content as untrusted data, prevent
  unauthorized disclosure through external requests, prefer primary sources,
  require citations for material external claims, and preserve local policy and
  project truth as authoritative when conflicts arise.

## Configuration validation

- [ ] A table-driven test visits every registered agent and structurally parses
  the generated Claude and Codex outputs.
- [ ] Tests cover default enablement, explicit opt-out, missing rationale,
  invalid values, overlay precedence, exact-once Claude tools, and explicit
  Codex enable/disable.
- [ ] Existing sync checks remain green for both runtimes.
- [ ] No test requires network access, a delegated agent, or the real user
  runtime directories.
- [ ] Validation and handback say configuration passed, while live availability,
  runtime enforcement, and instruction compliance remain unverified.

## Documentation

- [ ] Documentation directs maintainers to canonical Flow source and sync, never
  to hand-edit generated agent files.
- [ ] Documentation explains the global default, per-agent opt-out and rationale,
  task-explicit authorization, native runtime differences, and configuration-only
  proof boundary.
