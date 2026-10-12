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

## Post-merge review and release-gate follow-up

The first main release gate for merge `08e50be3` exercised 2,172 tests and failed
only because a wheelhouse-gated legacy smoke test still expected the retired
`runtime install-maf` command to succeed. The follow-up test now checks the
intentional retirement, generated surfaces and independently installed SDK
readiness. It passed both with the pinned SDK and with a base interpreter.

Codex's review of head `7d1d35b` completed at 2026-10-12 00:57:45 UTC
and identified two workflow findings. The authorized follow-up addresses both:

- [Approved revision-3 artifact integrity](https://github.com/andyconley/flow/pull/111#discussion_r4243956499):
  approvals record SHA-256 digests for required definition, solution, plan,
  implementation/handback, review and archive outputs. Verification and later
  execution/continuation/archive reject changed, missing or symlinked approved
  files. Old approved runs without required digests remain inspectable but
  require a new reviewed workflow to continue; they are never silently resealed.
- [Implementation approval retry](https://github.com/andyconley/flow/pull/111#discussion_r4243956500):
  retry from `handback_ready` skips the completed mark transition and starts
  review, while retaining artifact integrity checks.

Authorized `request-refinement` clears only current implementation evidence,
handback and review seals/gates, preserving earlier definition/solution/plan
approvals for the rework cycle. See [approval integrity](architecture.md#approved-artifact-integrity-revision-3).
The follow-up focused suite passes 23 tests, including seven provisioning tests, six new approval/retry regressions, and transactional source/config/launcher/pointer rollback checks. All fixtures use isolated destinations and no models. The earlier counts above describe their
recorded runs and do not claim validation of these lifecycle fixes. Offline
checks do not establish live acceptance. The live installation remains unchanged.

## Predecessor-upgrade bridge follow-up

A fresh review identified the first upgrade from an older updater: it swaps
source before it can know about new OpenHands provisioning. The follow-up adds
an installed-source/missing-marker bridge on `workflow execute`, explicit
`update` (without `--check`), and `bootstrap`. It binds the verified SDK interpreter and
re-executes the requested command. Checkout use and retired execution commands
do not activate it. User profiles and custom pinned Python are preserved.


Inspection remains free of installation side effects: `workflow status`,
`workflow runtime`, runtime readiness/smoke, and `update --check` report existing
state without provisioning. Workflow init, approve, archive and native-handoff
also do not activate the bridge because they do not require SDK execution.
Readiness reports a missing runtime; use `workflow execute`, explicit
`flow update`, or bootstrap to activate an unmarked installed upgrade.

Failure retains the prior launcher/configuration/runtime pointer and stdlib
inspection, while OpenHands-dependent commands report an error. `flow update`
retries repair. Source already deleted by the predecessor cannot be restored;
current new install/update paths still provision before swap with full activation
rollback. See [the migration boundary](openhands-migration.md#upgrade-through-a-predecessor-installer).

The bridge passes eight lifecycle tests, including actual isolated CLI activation, clean JSON after re-execution, all 39 role discovery links, and read-only command preservation. The focused bridge/install/approval/staging suite passes 30 tests. These fixtures contact no package index or model. The live installation remains untouched.

Release candidate and published verification now install the pinned SDK in their
CI environment before requiring all-target runtime smoke, and both verify the
OpenHands sync surface as an additional required check. Historical wheelhouse
fetching remains for archived tests and exact previous-release compatibility;
no release gate is bypassed or made optional.
