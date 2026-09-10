# Validation plan: role-method differentiation repair

## Deterministic checks

- Validate JSON-LD shape, source/locator fields, audience, unique ids, and
  bidirectional competency joins for every composed role.
- Assert the selected product-manager and quality-reviewer role instructions
  and replacement entry ids are present, and every superseded id is absent.
- Exercise the shared agent-body renderer for Claude/Codex source parity.
- Break one selected instruction, confirm the named contract test fails, then
  restore it and rerun the focused suite.

## Behavioral checks

Freeze the repair manifest before running either arm. It records prompts,
rubrics, model and effort, maximum turns and budget, treatment/control body
hashes, repository revision, dirty-tree fingerprint, and stopping rule.

For each role:

- primary treatment satisfies every distinctive item;
- unchanged-body control misses every distinctive item;
- treatment counter-case does not over-apply the method;
- all four records parse and complete without client error.

## Delivery checks

Run the Python 3.12 focused and full suites, `git diff --check`, Claude and
Codex user sync plus drift checks, static runtime smoke, and `flow doctor`.
Static runtime checks do not satisfy the four live-client checks already
tracked separately in `.flow/memory/STATE.md`.
