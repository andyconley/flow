# Implementation Handoff: Global Flow Agent Web Access Policy

## Start state

- Run: `agent-web-access-policy`
- Approved requirements: `requirements.md`
- Approved design: `solution.md`
- Approved implementation plan: `plan.md`
- Validation contract: `validation-plan.md`
- Expected release: v0.23.0, selected by semantic-release from a `feat` commit.

## Build order

1. Implement and test the pure resolver in `cli/agent_capabilities.py`.
2. Integrate layered policy loading and pre-write validation in `cli/sync.py`.
3. Make malformed overlay TOML fatal and update the existing fallback test.
4. Implement native rendering and bounded guidance in `cli/render.py`.
5. Add the framework default and remove manual web tools from the solution
   architect source.
6. Complete fake-home integration and atomicity coverage.
7. Add ADR, mapping table, migration examples, source/edit guidance, and
   configuration-only proof wording.
8. Run validation, independent security/quality review, and reconcile findings.
9. Use C-Lite handback/review gates, commit and push the accepted source, verify
   the automated v0.23.0 release, then archive.

## Guardrails

- Preserve `[[agents]]` replacement semantics; capability exceptions merge on
  their own key.
- Validate before `sync_outputs`, including before stale-file removal.
- Keep the Codex mode and tool boolean coupled.
- No catalog means byte-compatible legacy behavior.
- Require an explicit Claude `tools:` list for enabled and disabled agents when
  the catalog is active; omission can inherit runtime tools and is not a deny.
- Never edit generated runtime agent files or manually create release objects.
- Do not add skills, live web tests, credentials, arbitrary HTTP, or runtime
  enforcement to this slice.

## Required reviewers

- Security reviewer for the permission expansion and disclosure boundary.
- Test engineer for resolver, integration, and release evidence.
- Architect for domain/adapter separation and overlay precedence.
- Independent quality reviewer for acceptance.
