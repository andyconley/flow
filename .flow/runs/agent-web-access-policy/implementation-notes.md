# Implementation Notes: Agent Web Access Policy

## Product changes

- Added `cli/agent_capabilities.py` with the known boolean capability catalog,
  strict validation, independently layered exceptions, provenance, rationale,
  stable errors, and shared guidance.
- Updated `cli/sync.py` to resolve policy after the final agent merge and before
  desired output reaches `sync_outputs`. Malformed overlays now fail normally
  through the CLI without a traceback or partial write.
- Updated `cli/render.py` to normalize Claude web tools and emit the coupled
  Codex mode/tool mapping. Every governed Claude source must declare `tools:`,
  including disabled agents, because omission can inherit runtime tools.
- Added the global default to `scaffolds/default/flow.toml` and removed the
  solution architect's hand-authored web entries.

## Documentation and proof

- Added ADR 0003 and updated architecture/runtime adapter documentation with
  source, mapping, overlay, migration, rollback, and proof-boundary guidance.
- Added pure resolver tests and fake-home tests for the full inventory, native
  mappings, normalization, legacy behavior, exception precedence, re-enable,
  invalid policy, malformed overlays, missing tools, idempotence, atomicity,
  and required guidance clauses.

## Review correction

Independent review found that a disabled Claude agent with no `tools:` field
could inherit web tools. The renderer, tests, plan, ADR, and docs were corrected
to require an explicit list for enabled and disabled agents. Security and
quality re-review report no open findings.
