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
replace the framework candidate catalog. Eligible Ollama remains first for every
role within its declared tier, including lead-developer, data-engineer and test-engineer.
It is not limited to support work. Without an explicit user/project provider order,
the shipped `implementation_routing.hosted_preferences` uses Codex for lead-developer,
data-engineer, test-engineer and sre; Claude for other roles. These are practical
allocation defaults, not vendor capability claims. Explicit provider order and
role profile bindings retain precedence. Per-role hosted preferences can also be
overridden in user/project flow.toml. All defaults still obey candidate eligibility.
Native models use canonical role tiers; explicit runtime profile models win.
No model chooses a provider or silently changes an endpoint.

Ollama admission accepts declared `sdk_tool_calling` or the explicit candidate
setting `sdk_tool_use = "user-enabled-unverified"`, and requires an SDK context
of at least 16,384, the pinned SDK's own minimum. User enablement authorizes attempts;
it does not assert a passed test or change permissions. Reporting keeps that state
and unverified capability separate from routing eligibility. Advertised Ollama `tools` support
is not evidence of a successful Flow worker test. `workflow runtime --json` lists
local context and missing eligibility reasons. Profiles derive from machine-owned
`local_machine` settings; updates do not replace those with this laptop's values.

Eligible local workers use a machine-wide advisory lock at
`~/.flow/state/openhands-local-worker.lock`, held for the SDK task's duration.
One Flow local worker runs at a time across projects/processes. This does not
control unrelated Ollama clients. A busy slot routes a fresh assignment to the
fixed eligible hosted fallback. A failed local task returns its failure and a
partial-edit warning; the SDK coordinator can inspect and issue a fresh task,
which uses the fixed hosted fallback in that active SDK task executor. Failed work is never automatically replayed.
Explicit role profile bindings remain fixed and do not gain an implicit fallback.
Resume uses the original worker binding; unavailable local capacity rejects resume.

### Current new MacBook baseline (October 16)

The existing Llama 3.1 8B Q4_K_M uses 16,384 context, 2,048 output and a
13,312 summary threshold on this Mac only. An earlier 8K attempt failed SDK's
16K minimum before inference. Local `max_input_tokens` now also supplies Ollama's
native `options.num_ctx`; an SDK token budget alone did not set server allocation.
This machine's Ollama runtime override uses `reasoning_effort="none"`, because
SDK's default high reasoning caused Ollama to reject Llama as not supporting thinking.
Other machines/models retain their own explicit reasoning configuration.

The corrected bounded implementation/tool check was stopped by its memory guard
before any tool call/result: system swap increased from 10,894.62 to 11,899.25 MiB
(1,004.63 MiB) in approximately five seconds, and pressure changed from normal to
warning. The process was terminated and the model unloaded. This is a system-wide
observation under desktop load, not isolated attribution to the model. No user
applications were closed. No SDK tool capability was declared. Andy subsequently explicitly enabled Ollama
on this new MacBook using `sdk_tool_use = "user-enabled-unverified"`. It is eligible
as the primary implementation worker, with Codex as its fixed eligible fallback
and Claude for judgment-tier review. The stopped check remains unverified; memory
observations are warnings, not an authorization gate. No further model test was run.
Do not call this configuration validated memory-safe or tool-incompatible.
Studio's independent Gemma 64K settings are unchanged.

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
