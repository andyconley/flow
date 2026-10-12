# Stock specialist integration validation

This change starts from released v0.43.0 (`4b9fce64`) and uses OpenHands SDK/tools
1.54.0. Flow supplies role composition, profile configuration and SDK factories.
The SDK owns classification, task execution, workspace tools, ACP transport,
permissions, persistence and metrics. No custom execution controller is added.

## Regression and protocol evidence

Fifteen new pinned-SDK regression tests cover mixed local/native construction,
custom role context, nested skill package boundaries and project precedence, inheritance of a switched LLM, explicit role bindings,
project/profile registry isolation, stock classifier execution and switching,
explicit profile precedence, unchanged non-routing session fingerprints, routing
target binding changes, legacy child identifier compatibility, explicit invalid profile rejection, condenser safety across smaller/larger switches, native access acknowledgement and restricted SDK scope
rejection. The initial full run executed **2,200 tests**, with 81 skips and 23 failures/errors
caused by SDK provisioning network denial or localhost socket denial. A targeted
rerun recovered 22 of those with the verified interpreter and permitted test
sockets; the remaining interpreter-selection test passed when run under the
pinned interpreter, as the release gate does. Subsequent focused regressions
cover the final specialist and skill-loading changes. Remote PR/release checks
provide the authoritative full candidate run.

`tests/openhands_specialist_eval.py` runs actual stock TaskManager child
conversations. With the disposable ACP peer, both Claude and Codex factory
paths complete, handle an `allow_once` permission request and resume the same
SDK child conversation/native session. Four turns write the expected proof.
This is protocol evidence, not native subscription acceptance. CI runs it
without subscription access, credentials or model inference.

## Live acceptance

The benign fixture contains `numbers.txt` with `2 3 5`. Local coding is asked to
write `sum.txt`; native readers are asked to inspect the file and report its sum
without editing configuration or requesting new permissions. All SDK state and
npm caches are disposable. Existing authentication is reused in place. The
native profiles request Claude `plan` and Codex `read-only` modes. No native
configuration, global discovery, credentials, model configuration or access
grants are changed by the fixture.

- Native Codex through pinned `codex-acp@1.10.0`: completed with sum **10**;
  continuation completed using the same SDK child conversation. ChatGPT native
  authentication and `gpt-6-astra` were used.
- Native Claude through pinned `claude-agent-acp@0.63.0`: initialized and selected
  `plan`. The first attempt hit the existing subscription session limit. After
  its normal reset, the child completed with sum **10** and resumed the same
  conversation. The continuation used read-only `ls`/`Read`; no write or grant
  was requested and no paid API fallback or purchased capacity was used.
- Existing Ollama `gemma4-26b-dev` was observed loaded at **65,536** context.
  After correcting nested skill package discovery, the local child wrote
  `sum.txt` containing **10**, completed, and resumed the same child conversation.
  A real Ollama parent also used stock `task` to select a local coding child,
  select native Codex for verification, then resume that same Codex task. The
  persisted parent finished; `sum.txt` contained **10** and the same native
  child history contained two user turns. Two child conversations were created.

The initial Ollama attempts read the input but looped on directory inspection.
The compatible-endpoint comparison reached a completed SDK status with the
wrong requested outcome: its response addressed unrelated MCP instructions.
History exposed **312,913 characters** of reference documents misclassified as
permanent skill content, including nested synced skill references. The fix uses
SDK `load_available_skills`, `load_skills_from_dir(exclude_dirs=...)` and
`Skill.load` with actual package boundaries. The corrected fixture keeps the
same host skills and all reference files, with AgentSkills loaded progressively.
Its outcome is verified by the file contents, not just SDK completion status.
No model/server/global discovery configuration was changed.

The host's restricted shell initially denied SDK profile-home lock writes and
native npx/network startup. A reviewed live invocation with isolated SDK settings
started both native bridges. The outer execution environment still determines
actual containment. Raw host diagnostics stay in the task workspace, outside the
repository; native session identifiers and credentials are not publication
artifacts.

The stock classifier also completed a real local inference and selected the
coding category, switching to the inline compatible profile at the existing
Ollama `/v1` endpoint. Both tested profiles use the same physical model; this is
profile-routing acceptance rather than a comparison of model quality.

Final exact CI subset: **74 tests passed** before the added fresh-process resume regression, including the corrected generated
factory contract and all 15 specialist regressions. The deterministic task/ACP
fixture passes again after skill discovery changes. Sanitized acceptance is in
[acceptance/specialists/result.json](acceptance/specialists/result.json).

`tests/openhands_routing_resume_eval.py` passed with actual SDK classification,
file actions, pending confirmation and fresh Flow processes. Request models were
`initial`, `initial` (classifier), then `routed` for all three continuation calls.
An unconfirmed inspection made no model/tool call; confirmed actions retained the
same conversation and active model. A separate cold-process unit test verifies
that the active profile, smaller-context condenser cap and current dedicated
credential environment are restored. Both checks run without native access or
paid inference.

## SDK behavior and remaining limits

The tests verify child resume within the same TaskManager. In SDK 1.54.0 its
`_tasks` map is in memory. Persisted child conversations alone do not reconstruct
that map after a fresh parent process starts. A parent Flow stage can still
resume its persisted conversation and read prior delegation results, but an old
`task` resume identifier is not guaranteed callable in a new manager. Options
are to delegate a new continuation task using the prior result/context, keep a
stock parent conversation alive, or adopt an upstream SDK task-map persistence
improvement. Flow does not add a second task ledger to manufacture this feature.

ACP auto-approves native permission options; construction with a restricted SDK
tool/MCP scope is rejected because ACP capabilities cannot be checked. Native
`permission_requests` acknowledgement and existing execution modes remain in
force. `AlwaysConfirm` is not a native permission mediator, and stock task
confirmation behavior is distinct from OS containment. No scoped capability
check or host access boundary was removed. Remote-workspace delegation, native
write/permission requests on live accounts and automatic selection quality
across several live models are not validated by this fixture.
