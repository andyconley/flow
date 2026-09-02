# Security Review Summary

### Summary

- Verdict: PASS — approved for release
- Critical: 0
- High: 0
- Medium: 0
- Low: 0
- Release impact: No security blocker. The implemented configuration boundary satisfies the approved requirements; retain the stated runtime nonclaims.

### Findings

- None open.

### Resolved Findings

#### RESOLVED Quality review major: disabled Claude agent could inherit all tools

- Prior issue: Under an active catalog, a disabled custom or replacing Claude
  agent without source `tools:` could omit the generated allowlist. Claude could
  then inherit all subagent tools even while the generated body claimed the
  role was local-only.
- Resolution: `cli/render.py:295-304` now requires an explicit source `tools:`
  list for every Claude agent with an effective capability decision, enabled or
  disabled. `tests/test_flow.py:2013-2037` proves a rationale-backed disabled
  replacement without `tools:` fails and preserves the existing output byte for
  byte. `docs/architecture.md`, `docs/runtime-adapters.md`, and ADR 0003 now
  state that omission is not a denial.
- Disposition: Closed. The opt-out is fail-closed and no longer depends on
  omitted Claude frontmatter.

#### RESOLVED Prior Low: guidance tests checked only the marker

- Prior issue: A future edit could preserve the policy marker while weakening
  the task-authorization, untrusted-content, disclosure, source-quality,
  local-truth, or bypass safeguards.
- Resolution: `tests/test_flow.py:1729-1752` defines semantic assertions for
  every approved enabled and disabled clause. The complete-inventory test
  applies enabled assertions to Claude and Codex at
  `tests/test_flow.py:1780-1781`; the opt-out test applies disabled assertions
  to both at `tests/test_flow.py:1877-1878`.
- Disposition: Closed. Security behavior remains instruction-level, but its
  generated configuration contract is now regression-tested.

### Verified Security Properties

- `cli/agent_capabilities.py:138-198` accepts only the typed `web_research` catalog and the fixed `explicit-task-or-brief` authorization mode; unknown capabilities, fields, and invalid types fail closed.
- `cli/agent_capabilities.py:215-312` validates override identity, final-inventory membership, uniqueness, booleans, and nonblank rationales. A true override is accepted only when it re-enables a lower denial.
- `cli/agent_capabilities.py:315-377` resolves framework exceptions before user exceptions against the final merged inventory. A separately keyed framework denial therefore survives an unrelated same-name agent replacement.
- `cli/sync.py:181-239` resolves policy after overlay/agent merging. Malformed overlay TOML is fatal instead of silently discarding exceptions.
- `cli/sync.py:856-913` resolves and renders the complete desired target before `sync_outputs` can mutate managed files.
- `cli/render.py:285-323` removes duplicate/manual Claude web tools, preserves unrelated tools, emits exactly one grant pair when enabled, removes both when denied, and rejects every catalog-governed source without an explicit tools list.
- `cli/render.py:326-368` emits the coupled Codex grant (`web_search = "live"`, `tools.web_search = true`) or explicit denial (`web_search = "disabled"`, `tools.web_search = false`). Denial does not rely on parent-setting omission.
- `cli/agent_capabilities.py:17-37` gives both adapters the approved instruction boundary: task/brief authorization, untrusted-content handling, disclosure prohibition, primary-source/citation discipline, local-truth precedence, and no alternate-tool bypass for disabled agents.
- `scaffolds/default/agents/solution-architect.md` no longer carries a second hand-authored web-tool authority; the manifest policy and renderer are authoritative.
- Documentation and ADR language consistently distinguish configuration proof from live provider behavior and describe generated runtime files as replaceable outputs.

### Validation Evidence Reviewed

- `/opt/homebrew/bin/python3.12 -m unittest tests.test_agent_capabilities` — 9 tests passed.
- Ten focused `FlowCliTests` covering the full inventory, legacy mode, Claude normalization, explicit empty tools, opt-out, overlay denial preservation, rationale-backed re-enable, pre-write rejection, enabled missing-tools rejection, and disabled missing-tools rejection — all passed.
- The pre-write sentinel test at `tests/test_flow.py:1937-1993` verifies that invalid policy leaves existing agent output and stale managed files byte-identical for both runtime targets.
- The inventory test at `tests/test_flow.py:1754-1795` parses all thirteen Claude and Codex outputs, asserts native grant fields and required guidance clauses, and proves repeat sync is byte-identical.
- Re-review total: 19 focused tests passed (9 resolver and 10 Flow integration tests).

### Unverified Runtime Behavior

- Live web retrieval, provider/account entitlement, administrator policy, and client interpretation of generated settings were not tested.
- Task-level authorization and compliance with the generated guidance remain behavioral controls, not per-invocation technical isolation.
- Disclosure prevention, prompt-injection resistance, and disabled-agent refusal were not exercised through delegated live agents.
- These are approved nonclaims for this slice. Evidence may say **web capability configuration passed**; it must not say web access, runtime enforcement, or behavioral compliance passed.

### Positive Observations

- Capability intent is resolved once and adapted natively, preventing Claude/Codex policy drift by construction.
- Opt-outs are stored outside replaceable agent entries, and higher-layer re-enable is explicit and rationale-bearing.
- Codex denial is redundant in the safe direction: both mode and tool exposure are disabled.
- Invalid or malformed policy fails before output writes, avoiding a partial synchronization that silently broadens access.
- External content is explicitly treated as untrusted data and cannot override local policy or project truth.

### Recommendations

- During release handback, preserve the configuration-only wording and list live enforcement as unverified.
- If Flow later needs stronger least privilege, design task-scoped runtime grants as a separate capability; do not weaken or remove the current instruction boundary as a shortcut.
