# OpenHands implementation policy routing

`openhands_policy.py` is the pure binding adapter between existing Flow policy
and OpenHands specialist factories. `openhands_accounting.py` supplies a checked
SDK task-tool adapter; the SDK TaskManager still owns task execution, confirmation,
conversation persistence and results. There is no MCP bridge or native coordinator.

## Defaults and customization

Define, solution and plan slash commands invoke the current host's native Flow
agents. The host coordinates and obtains approvals. Implementation defaults to
`openhands-coordinator`, a stock SDK Agent using the canonical lead-developer Codex
model and reasoning tier (currently gpt-5.6-terra / medium) through direct OpenAI
subscription authentication. Its sole execution tool is checked specialist task
dispatch. Finish/think are the SDK's normal built-ins.

Each worker resolves separately. Explicit `[roles.NAME].profile` bindings win.
Otherwise `provider_selection` is merged with the existing monotonic policy merger,
using framework, user and project layers. Administrator `provider_candidates`
replace the framework candidate catalog. The existing selector filters enabled
candidates for edit capability, role tier and policy eligibility, then ranks
Ollama before Claude before Codex (hosted ordering may be customized). Native model
and effort policy comes from canonical agent tiers; an explicit runtime profile
model wins. Candidate catalog native model strings are not substituted for the
role-specific native model. Configuration eligibility is not authenticated/live
availability; failure is reported without silent provider fallback.

Historical Ollama structured-edit capability is not an SDK tool-use grant.
Automatic local selection requires `sdk_tool_calling` in its candidate capabilities
and a compatible local runtime profile. A profile is derived from existing
`local_machine` model/context settings when present; it does not pull a model,
start Ollama or assert model quality. Explicit worker profile bindings are also
supported. Without suitable local eligibility, the shipped order usually selects
Claude workers with different per-role models. Mixed providers occur when policy
eligibility or explicit role bindings select different providers, not by forced
round-robin balancing. For example `[roles.test-engineer] profile = "codex"`
keeps other policy-selected specialists on Claude. With the current Mac's historic
llama3.1:8b declaration, no automatic Ollama SDK worker eligibility is assumed.

Built-in profiles merge beneath user/project runtime.toml; no existing files are
rewritten. Existing default/stage/role/profile overrides remain visible. Native
profiles cannot coordinate implementation: use them on worker roles instead.
Local SDK coordinator profiles are allowed but explicitly selected by the user.
Do not use `[roles.lead-developer].profile` to configure the coordinator; use
`[stages.implement].profile`, leaving that role's binding for its worker.

## Human sign-in, never automatic

The pinned SDK supports direct OpenAI subscription LLMs, not Claude subscription
LLMs. This uses subscription access, not API credits. Run its supported interactive
sign-in yourself with Flow's installed Python interpreter (shown in
`~/.flow/config.toml`):

```python
from openhands.sdk import LLM
llm = LLM.subscription_login(vendor="openai", model="gpt-5.6-terra")
```

This call performs the SDK's consent and browser OAuth flow; it does not send a
model prompt. Do not approve it automatically or copy native CLI credentials.
The SDK manages `~/.openhands/auth` (or `OH_PERSISTENCE_DIR/auth`). Flow readiness
checks only file existence; it never reads or refreshes credentials. Actual SDK
execution loads/refreshes them through the SDK, and fails on absent/invalid login.
No API-key or endpoint override is accepted on the subscription coordinator.
The SDK subscription backend does not support output-token caps; Flow does not
claim those caps are enforced. Supported reasoning effort is passed to the SDK.
Native ACP workers receive model selection but not Flow reasoning effort; their
harness settings govern effort and tool permissions.

## Dispatch and permission boundaries

The coordinator can request only roster role names. Its task action schema rejects
extra provider/profile/model fields. The executor maps roles to fixed factory IDs
and rejects other global registry names and unknown/cross-role resume IDs.
Bindings contribute to the workflow session fingerprint; configuration changes
require a new session. Worker role-file drift after binding fails at construction.
All Flow workers are leaves: no task tool, model-switch tool or Flow child roster.
SDK task dispatch requires explicit host confirmation; native ACP permissions
still use the terminal proxy. No automatic consent, credentials or persistent
permission settings are introduced. Missing login/terminal preflight leaves the
workflow stage unchanged. Plan and verification gates remain in the lifecycle.

These are dispatch controls, not OS containment. Native workers may have native
subagents or shell commands permitted by their existing harness. Flow cannot claim
to prevent a shell-authorized worker launching another CLI. SDK tool restrictions
are not translated into native permissions. Existing explicit legacy
stock-openhands permission settings remain user-owned, never new defaults.
