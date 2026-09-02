# Testability: agent web-access policy

- Owner role: test-engineer
- Date: 2026-09-02
- Recommended level: deterministic source-to-rendered configuration integration test, with one focused policy-validation negative case.

## What the test can prove

The release boundary is configuration, not a live tool call.  A test can prove that the canonical policy resolves consistently after manifest/overlay merge and that the two generators render their respective native declarations.  It cannot prove that a particular Claude or Codex host exposes those tools, that account or administrator policy permits them, or that a delegated agent successfully invokes them.

The validation result must therefore say **configuration and generated artifacts passed**.  It must not say **web access passed**, **live web research works**, or equivalent.

## Smallest sound test set

Keep this in `tests/test_flow.py`, next to the existing fake-home sync and user-overlay coverage.  Reuse the actual framework manifest, `flow sync <target> --user`, the existing overlay helper, and `flowtoml.read_toml`; do not build a second mock renderer or inspect the real user runtime directories.

### 1. Inventory and native-mapping integration test

One table-driven test should:

1. Read the canonical scaffold manifest and obtain the full `[[agents]]` inventory.
2. Assert the one shared semantic default is enabled.
3. Sync both targets into a fake home.
4. Iterate every manifest agent by name, collecting it in a `visited` set.
5. For every effective default-enabled agent:
   - parse its generated Claude Markdown frontmatter and assert `WebSearch` and `WebFetch` each occur exactly once;
   - parse its generated Codex TOML and assert the chosen native web-search setting is explicitly enabled (for example, the planned `live` mode), rather than searching for Claude tool names.
6. Assert `visited == {registered agent names}`.  This makes a newly added role fail the test if generation, a lookup, or a capability mapping skips it.
7. Assert the shared instruction text is present in both generated agent bodies: web research is only for an explicitly assigned external/current-research task (or a named Flow research question), and local evidence remains preferred otherwise.

This is a single source-to-generated test, rather than thirteen role-specific tests.  It automatically covers the global default and full inventory while retaining per-agent failure output.

### 2. Explicit opt-out and rationale validation

In the same test class, use a temporary copy of the manifest or a small resolver-level fixture to set one representative registered agent to `web_research = false` and provide a non-empty rationale.  Render both adapter outputs and assert:

- Claude has neither `WebSearch` nor `WebFetch`.
- Codex has an explicit native disable, not an omitted setting that could inherit the parent session's capability.
- The generated role guidance identifies it as local-only and explains what to do when given a web-required task (surface the conflict or route research to an eligible role).

Pair that with one negative assertion: the same opt-out with an empty, missing, or whitespace-only rationale must raise the configuration-validation error before either adapter is rendered.  The test should assert the error identifies the agent and missing rationale.

This proves both the exception behavior and that an opt-out cannot be introduced silently.  It deliberately does not require a permanent opted-out built-in role merely to test the mechanism.

### 3. Overlay precedence integration test

Extend the existing fake-home user-overlay agent helper so an overlay entry can declare the capability field and rationale.  Replace one framework agent in `~/.flow/user/flow.toml` with an otherwise valid overlay agent that explicitly opts out, then sync both targets.

Assert that the overlay version is the generated source (existing managed-manifest origin assertion), and that its effective output is disabled in both adapters as above.  This proves that capability resolution occurs **after** the supported user-overlay merge and that an explicit exception wins over the global default.  It does not expand the public authoring scope: it validates already-supported merge behavior rather than promising a separate overlay feature.

## Determinism rules

- Use only local fixture files and generated strings; no network, browser, account, or delegated-agent invocation.
- Parse outputs structurally: Flow's frontmatter parser (or an equivalent list assertion) for Claude and `flowtoml.read_toml` for Codex.  Do not use broad substring checks as the primary proof.
- Assert enabled and disabled values explicitly.  Absence is not a valid Codex opt-out because native configuration may inherit parent settings.
- Keep the expected Codex representation centralized in one test helper/constant.  The test should assert semantic mapping to the selected native mode, not pretend Codex supports literal `WebSearch`/`WebFetch` names.
- Run the existing sync freshness checks after the focused test; they protect generated-file drift but do not replace this policy test.

## Coverage matrix

| Policy condition | Claude assertion | Codex assertion | Test |
|---|---|---|---|
| Global default | Both named web tools exactly once for every inventory agent | Native web research explicitly enabled for every inventory agent | Inventory and native-mapping |
| Per-agent opt-out | Neither named web tool | Explicit native disable | Opt-out and rationale |
| Missing opt-out rationale | Configuration error before rendering | Same shared error | Opt-out and rationale |
| User overlay opt-out | Overlay output has neither named tool | Overlay output explicitly disables native setting | Overlay precedence |
| Task authorization rule | Generated guidance limits use to explicitly assigned research | Same generated guidance | Inventory and native-mapping |
| Runtime capability | Not asserted | Not asserted | Out of scope |

## Existing coverage and gaps

Existing tests already provide the right harness pieces:

- `test_sync_claude_generates_the_full_runtime_surface` and `test_sync_codex_generates_skill_runtime` prove fake-home generation but currently inspect only models and general surface presence.
- The user-overlay tests prove same-name agent replacement and generated source origin, but not a resolved capability override.
- Runtime-smoke tests correctly classify delegated role invocation as `manual_required`; they should continue to do so rather than being repurposed as a web-access claim.

The proposed tests fill the policy-resolution and adapter-parity gaps at the lowest adequate level.  A live research smoke test remains intentionally deferred because it would add network and host-policy variability without improving the agreed configuration acceptance boundary.
