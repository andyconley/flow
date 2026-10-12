# Agent distribution validation

The authoritative shipped roster contains 13 roles, rather than an inferred
14. Offline generation produced 13 Claude Markdown definitions, 13 Codex TOML
definitions, and 13 OpenHands Markdown definitions: 39 discoverable files backed
by 39 Flow-managed files. All discovery files used relative symlinks in the
isolated destination. A managed-copy fallback was tested separately.

The identical role set for each target is: architect, business-analyst,
data-engineer, lead-developer, product-manager, quality-reviewer,
security-reviewer, solution-architect, sre, support-lead, tech-writer,
test-engineer, ux-specialist. User additions are merged by the existing manifest
pipeline; the extra-role fixture validates an added overlay definition and its
subsequent update/removal conflict.

## New output and install checks

`tests/test_agent_distribution.py` adds 12 tests. They verify all 39 definitions,
TOML field/instruction round trips including backslashes, triple quotes and
non-BMP Unicode, all three clean drift checks, idempotent symlink installation,
managed-copy fallback, a repeated isolated release bootstrap install, custom
agent/skill preservation, edited generated skill/agent preservation, redirected
and dangling-link rejection, missing-owned-backing repair, user source updates,
stale edit preservation, and conservative migration from hashless manifests.

The pinned SDK's real `load_project_agents` discovers all 13 generated OpenHands
definitions. A selected lead-developer plus 12 stock registry factory
constructions cover the full roster. Child agents have instructions and tools,
inherit the selected local profile, and omit the task tool for an implicit empty
child roster. These checks construct agents but never invoke a model.

The CI workflow `openhands-runtime.yml` installs exactly SDK/tools/workspace/
agent-server 1.54.0 and runs these output checks with the existing SDK, workflow,
capability and renderer regressions. The latest local focused run passed 36
checks. Existing documentation/expertise checks passed 61 tests, and new local
documentation links were checked.

## Existing regression suite

The merged source ran 2,172 existing and new tests under Python 3.12 with the
pinned OpenHands environment. The restricted host passed 2,098, skipped 72, and
blocked two retained-runtime cancellation fixtures from binding ephemeral
localhost sockets. Those exact two fixtures passed when rerun with loopback
access: no code failure remained. They connect only to a silent local fixture;
they do not contact Ollama or a native provider. This is separate from the 36
focused output/runtime checks above.

No live model call, native authentication change, active process restart or live
installation update was part of these checks. Native Claude/Codex callable
formats were checked against their pinned source contracts; real native child
invocation and provider model/effort behavior remain live acceptance checks.
OpenHands's stock external file-discovered definitions have no tools; Flow's
contextual stock factories provide the configured local tools.

## Reproduce

Use an isolated Python 3.12 environment with
`runtime/openhands/requirements.txt` installed:

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True OPENHANDS_SUPPRESS_BANNER=1 \
  python -m unittest tests.test_agent_distribution \
    tests.test_openhands_sdk_construction tests.test_openhands_workflow \
    tests.test_agent_capabilities tests.test_expertise_advisory_render
python -m unittest discover -s tests -p 'test_*.py'
```

Install tests create temporary homes and never write the current user's native
agent directories. Restricted hosts may need loopback access for the two
cancellation fixture tests. Refer to [the migration contract](agent-distribution.md)
for the coordinated live installation step and conservative legacy conflicts.
