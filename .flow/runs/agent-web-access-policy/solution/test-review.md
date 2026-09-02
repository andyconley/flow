# Test Review: agent web-access policy

- Reviewer role: test-engineer
- Date: 2026-09-02
- Verdict: **Approve with the test-contract refinements below.** The recommended resolver plus two native adapters can satisfy the approved configuration-only acceptance criteria without a network or delegated-agent test.

## Review outcome

The design has the right test boundary:

- A pure resolver owns the semantic decision, layered exceptions, and invalid-policy failures.
- The fake-home adapter test proves that effective policy reaches both generated runtime forms.
- Runtime smoke remains `manual_required`; it must not be relabeled as web-access validation.

The keyed override table is specifically better than fields on `[[agents]]` for the required overlay behavior.  A same-name overlay body replacement cannot erase a framework local-only exception merely by omitting a capability field.  The planned explicit re-enable rule also avoids an accidental widening of a lower-layer denial.

## Necessary refinements before implementation

1. **Make `resolve_agent_capabilities` a stable, directly testable pure interface.** It should accept the framework policy, overlay policy, and final post-merge agent names; return the effective mapping keyed by agent name; and raise one actionable validation exception before adapter output is built.  Tests must not need to infer semantics from renderer output alone.

2. **Validate the entire merged policy before either target writes.** `flow sync claude --user` and `flow sync codex --user` are separate commands, but each must reject invalid capability configuration before calling `sync_outputs`.  This prevents a malformed override from producing one partially updated runtime surface.

3. **Specify the generated guidance as named, bounded markers.** Define one enabled marker and one disabled marker (or constants/template identifiers) that tests can assert once in each generated body.  Do not assert the full prose verbatim.  The markers must cover the explicit-task authorization rule, local-first behavior, external-content-as-untrusted-data, and local-only reroute behavior.

4. **Keep overlay support truthful in docs and tests.** The feature being added is a capability override record in an already-supported user overlay, not an unverified directory convention.  The test must create `~/.flow/user/flow.toml` directly and prove the existing agent-body replacement plus separately keyed policy precedence.  Documentation should say framework defaults cannot be redefined by an overlay in this slice.

5. **Parse both generated representations structurally.** Claude assertions should use `parse_frontmatter` and exact list counts.  Codex assertions should parse TOML and inspect `web_search` plus the nested `tools.web_search` boolean.  Absence is never accepted as the Codex denial proof.

6. **Preserve the current source-compatibility test.** Add a negative adapter test for a user-added/replaced Claude agent with no `tools` list.  It must fail before write with source path and remediation.  This is a stated design risk and otherwise remains unproven.

## Implementation-ready test contract

### Resolver unit tests — `tests/test_agent_capabilities.py`

Use fixture dictionaries only; do not write a home directory or invoke sync.  Each case must assert either the exact effective boolean or a deterministic validation error containing the agent/capability and rule violated.

| Case | Framework policy | Overlay policy | Expected result |
|---|---|---|---|
| Default grant | `default = true`, no override | none | Every final-inventory agent resolves `web_research = true` |
| Framework denial | false override + non-blank rationale | none | Target agent resolves false; other agents retain true |
| Invalid denial | false override + blank/missing rationale | none | Reject before resolution/rendering |
| Overlay omission | framework false override | overlay replaces same-name agent body but has no override record | Framework denial remains false |
| Overlay denial | no lower denial | overlay false + rationale | Target resolves false |
| Explicit re-enable | framework false + rationale | overlay true + rationale | Target resolves true |
| Ambiguous enable | default true/no lower denial | overlay true + rationale | Reject redundant re-enable |
| Invalid schema | non-boolean default/enabled, unknown authorization, unknown capability | any | Reject each value by rule |
| Invalid identity | duplicate `(agent, capability)` per layer or unknown final-inventory agent | any | Reject before rendering |

The resolver test fixture must include both a framework and final merged inventory so it proves that validation happens after agent replacement/addition rather than against framework names only.

### Adapter and sync integration tests — `tests/test_flow.py`

Use the existing writable-scaffold + fake-home helpers.  Call both `flow sync claude --user` and `flow sync codex --user`; inspect only the fake home.

1. **`test_web_capability_default_renders_for_full_agent_inventory`**
   - Read the actual canonical manifest and assert its `web_research.default` is true.
   - Sync both targets; build expected names from the post-merge `[[agents]]` inventory and assert the generated filename sets match it.
   - For every generated agent, assert Claude `tools` contains each of `WebSearch` and `WebFetch` exactly once; assert Codex parses to `web_search = "live"` and `tools.web_search = true`.
   - Assert the enabled-guidance marker occurs exactly once in both generated bodies.
   - Run a second sync and assert byte-identical agent outputs, proving no repeated tool/guidance mutation.

2. **`test_framework_opt_out_renders_explicit_local_only_policy`**
   - In the writable scaffold, inject one valid framework false override with a rationale.
   - Sync both targets.
   - Assert that one Claude agent contains neither web tool and one Codex agent parses to `web_search = "disabled"` and `tools.web_search = false`.
   - Assert the disabled-guidance marker appears once and the enabled marker does not.

3. **`test_overlay_body_replacement_preserves_framework_web_denial`**
   - Start with the framework denial fixture above, then replace the same agent body through the existing fake-home overlay helper without a capability override.
   - Assert the managed manifest records the overlay source, while both generated configurations remain explicitly disabled.  This is the critical regression test for body-replacement precedence.

4. **`test_overlay_explicit_reenable_replaces_framework_web_denial`**
   - Start with the same lower denial, add the overlay keyed true override with rationale, and sync both targets.
   - Assert both generated forms are explicitly enabled and use the enabled guidance.  The test must not pass merely because the framework default is true.

5. **`test_invalid_web_capability_policy_fails_before_runtime_write`**
   - Parameterize blank rationale, redundant overlay true, duplicate override key, and unknown override agent/capability.
   - Seed sentinel generated agent files in fake home, run each target sync, assert non-zero exit/actionable error, and assert the sentinels remain unchanged.  This proves fail-closed validation before writes.

6. **`test_web_enabled_claude_agent_requires_declared_non_web_tools`**
   - Add or replace an overlay agent with no `tools` list under an enabled effective policy.
   - Assert sync fails before writing that agent and names the source path plus required correction.

These are integration tests, not live web tests.  They should be the only tests that inspect emitted native syntax; resolver tests should remain runtime-agnostic.

## Acceptance-criteria traceability

| Acceptance concern | Proving test |
|---|---|
| One global default covers all current and future registered roles | Full-inventory default integration test |
| Claude has both native web tools exactly once | Full-inventory and opt-out integration tests |
| Codex has equivalent explicit native capability | Full-inventory and opt-out integration tests |
| Documented source opt-out wins everywhere | Framework opt-out integration + resolver denial tests |
| Missing rationale is rejected | Resolver invalid-denial + fail-before-write integration cases |
| Overlay cannot silently erase denial | Overlay body-replacement preservation test |
| Intentional overlay re-enable is explicit | Resolver re-enable + overlay re-enable test |
| Explicit-task-only guidance remains present | Enabled/disabled guidance-marker assertions |
| No claim of live tool access | Test/handback wording and unchanged runtime-smoke `manual_required` classification |

## Validation command set

Run the focused resolver module and integration cases first, then the full suite:

```text
python -m unittest tests.test_agent_capabilities
python -m unittest tests.test_flow.FlowTests.test_web_capability_default_renders_for_full_agent_inventory ...
python -m unittest discover -s tests
```

The exact test-class path can follow repository convention during implementation.  No test command may make a network call, invoke a live browser, or delegate a role.  Release evidence should report the passing configuration tests and explicitly retain host availability, account policy, and actual tool invocation as unverified runtime risks.
