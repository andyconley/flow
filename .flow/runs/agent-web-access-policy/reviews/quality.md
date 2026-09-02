# Architecture and Acceptance Quality Review

## Verdict

**APPROVE — 0 open findings. Web capability configuration passed.**

The implementation matches the approved capability boundary, overlay
precedence, Claude and Codex native mappings, compatibility contract, and
configuration-level acceptance criteria. The previously identified Claude
fail-closed defect is resolved and covered by a no-write regression test. The
current 789-test suite passes.

This verdict is intentionally limited to configuration output. It does not
claim live provider access, runtime enforcement, instruction compliance,
disclosure prevention, delegated behavior, or network availability.

## Findings and Dispositions

No open critical, major, or minor findings.

### Resolved major — opted-out Claude agent without `tools:`

- Previous issue: an opted-out custom or replacing Claude agent whose source
  omitted `tools:` could inherit available subagent tools despite local-only
  guidance.
- Correction: `cli/render.py` now requires an explicit source `tools:` list for
  every Claude agent with an effective capability decision, whether enabled or
  disabled. The check occurs during rendering before generated files are
  written.
- Regression evidence:
  `test_disabled_custom_claude_agent_without_tools_fails_before_write` creates
  a rationale-backed denial, replaces the source with a no-`tools` agent, seeds
  a sentinel generated file, and proves sync fails without modifying it.
  `test_catalog_governed_custom_claude_agent_without_tools_fails_immediately`
  covers the enabled/default case.
- Contract evidence: `docs/adr/0003-semantic-agent-capabilities.md`,
  `docs/runtime-adapters.md`, and `docs/architecture.md` now document that the
  explicit-list precondition applies to opted-out agents because omission may
  inherit runtime tools.
- Disposition: **resolved and verified**.

## Acceptance Traceability

| Area | Verdict | Evidence |
|---|---|---|
| One reusable default for the full inventory | PASS | `scaffolds/default/flow.toml`; complete-inventory fake-home test visits all thirteen agents |
| Separate overlay-safe exceptions | PASS | `cli/agent_capabilities.py`; framework denial, omitted overlay entry, same-name body replacement, and rationale-backed re-enable tests |
| Strict schema and rationale validation | PASS | Resolver tests cover default type, authorization, unknown capability/agent, duplicates, and nonblank rationale |
| Resolve and validate before writes | PASS | `cli/sync.py`; invalid-policy, malformed-overlay, and missing-Claude-tools sentinel tests |
| Claude enabled mapping | PASS | Generated `tools:` preserves unrelated tools and contains `WebSearch` and `WebFetch` exactly once |
| Claude disabled mapping | PASS | Web tools are removed from explicit lists; a missing source list fails closed before writes |
| Codex enabled/disabled mapping | PASS | Generated TOML parses to `web_search = "live"` plus `tools.web_search = true`, or `"disabled"` plus `false` |
| Task-explicit authorization | PASS | Shared enabled guidance requires an explicit external/current research question in the task or brief and rejects availability alone as authorization |
| Untrusted-content and disclosure boundaries | PASS | Guidance-content assertions cover instruction distrust, sensitive-data limits, primary-source preference, citations, and local source-of-truth precedence |
| Documentation and durable decision record | PASS | ADR 0003 and runtime/architecture docs describe source ownership, resolution, native mappings, compatibility, rollback, and proof limits |
| Configuration-only claims | PASS | Requirements, plan, handoff, validation plan, ADR, and runtime docs preserve the approved nonclaims |
| Regression health | PASS | 12 focused tests and the full 789-test suite passed; review artifact passes `git diff --check` |

## Architecture Review

- Domain boundary: PASS. `cli/agent_capabilities.py` owns semantic capability
  resolution; `cli/sync.py` owns manifest layering and pre-write orchestration;
  `cli/render.py` owns provider-native representation.
- Overlay durability: PASS. Capability overrides merge separately from agent
  body replacement. Omission preserves a lower-layer denial, while an explicit
  rationale-backed entry can re-enable the agent.
- Fail-closed behavior: PASS. Invalid policy, malformed overlay input, and
  ambiguous Claude source tooling fail before stale-file removal or output
  replacement.
- Compatibility: PASS. Manifests without the capability catalog retain legacy
  rendering. Catalog-governed custom Claude agents must declare `tools:`, an
  intentional and documented validation boundary.
- Reversibility: PASS. The manifest, resolver, render mappings, and guidance can
  be reverted together and generated adapters resynced; no persistent data
  migration is introduced.
- Decision durability: PASS. ADR 0003 records the capability model, precedence,
  provider mappings, consequences, alternatives, and rollback.

## Validation Performed

- Read every requirements/plan evidence file and every changed product file
  listed in `briefs/implementation-quality-review.md`.
- Reviewed the delta that fixed the prior major finding, including the renderer,
  regression test, guidance assertions, ADR, runtime-adapter docs, and
  architecture docs.
- Passed: 12 focused resolver and Claude fail-closed tests in 0.643 seconds.
- Passed: `python3.12 -m unittest discover -s tests -p 'test_*.py'` — 789 tests
  in 179.172 seconds.
- Passed: `git diff --check` for this review artifact.

## Release Decision

Architecture and acceptance-readiness review approves release of the
configuration change, subject to the independent security verdict and the
release lane's remaining checks. The approved acceptance statement is:
**web capability configuration passed**.
