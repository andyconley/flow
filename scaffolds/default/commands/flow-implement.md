# flow-implement

Implement the approved plan with actual code and appropriate tests. Report evidence, limitations and remaining work in the handback.

Flow owns this workflow stage and its outputs. OpenHands owns execution, tools,
conversation history, retries and specialist delegation. Do not rebuild a Flow
manager, file broker, provider loop, token/rate gate or execution ledger.

## Enter and execute

After explicit plan approval, hand the approved artifacts and task to OpenHands:

```sh
flow workflow execute <work-id> --stage implement --task-file <task.md>
```

The default implementation coordinator is a normal OpenHands SDK Agent powered
by the existing machine-local Ollama profile. It has a checked task tool only;
OpenHands owns planning turns, delegation, execution history and continuation.
Claude and Codex native harnesses are specialist workers, never the implementation
coordinator. Native implementation handoff is refused.

OpenHands chooses among the listed role/provider targets, such as
`lead-developer--ollama-local`, `lead-developer--codex-hosted` and
`lead-developer--claude-hosted`. Flow validates configured eligibility and exposes
the roster; it does not choose the provider for a qualified task. Role-only calls
retain local-first and role-specific hosted preferences. Explicit role profiles
restrict that role. Worker factories cannot accept arbitrary models/endpoints or
delegate through Flow. The checked task tool rejects names outside its roster,
including unrelated SDK registry entries. After failure, inspect partial edits
before requesting a fresh task on another listed provider; no automatic replay.

Built-in profiles and implementation defaults require no handwritten runtime.toml.
Existing default, stage, role and profile settings remain authoritative; an old
native coordinator setting fails with instructions to bind it to worker roles.
The Ollama profile derives from existing local_machine settings. Missing local
configuration fails closed; it never permits host-native implementation.
An explicit coordinator profile does not override every worker's provider.

Inspect `flow workflow runtime --json` for the coordinator and worker bindings.
The local SDK coordinator needs no OpenHands subscription login. Claude and Codex
ACP workers use their existing native logins and permissions. Do not initiate
login, copy credentials, approve consent or use API billing on the user's behalf.
Missing configuration or a required human terminal fails before stage entry.

SDK task calls inherit the supported SDK automatic confirmation default. Explicit
`workspace.confirmation="always"` retains `--confirm-pending` / `--reject-pending`;
a resumed conversation re-asserts this current default rather than trusting a
persisted policy from an older binding. Native workers default to
`permission_requests="stock-openhands"`; explicit `interactive` uses human
terminal choices. Install/update removes existing overrides by default so the
scope inherits these automatic defaults; `flow defaults-review --check` previews
the pending removal and backup/recovery is the opt-out for a given run. Native
automatic approval can persist native permission rules. Workers inherit the
actual outer containment; a working directory is not an OS sandbox or a
shell-launch prohibition.

## Durable outputs

Write these files under `.flow/runs/<work-id>/`:

- `implementation-evidence.md`
- `handback.md`

For verification-v1 workflows, the host runs `flow workflow check` after execution
returns to create `verification.json` and captured logs. Specialists must not
create, edit, or synthesize those host-owned records. Link the expected record
from the handback and state that host verification is pending until it exists.

Use specialist roles, project skills, context and existing approved artifacts as
needed. SDK TaskToolSet handles configured specialist delegation. Record actual
results and unresolved questions; a model response alone does not approve work.

## Approval and continuation

After the user/operator has reviewed the outputs:

```sh
flow workflow approve <work-id> --stage implement
```

Approval records implementation handback and enters review. It does not accept
the review, archive, merge, push or deploy.

Inspect progress with `flow workflow status`, `flow run history` and SDK outcome
artifacts. Pause/block/resume through ordinary Flow lifecycle transitions.

Use the active runtime memory provider as companion context when available.
Verify material claims against canonical project artifacts and code.

Follow `standards/git-commits.md` for any authorized commits.
