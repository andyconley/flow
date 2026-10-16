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
by the SDK's direct OpenAI subscription LLM. It has a checked task tool only;
OpenHands owns planning turns, delegation, execution history and continuation.
Claude and Codex native harnesses are specialist workers, never the implementation
coordinator. Native implementation handoff is refused.

Provider bindings are resolved independently for each role by deterministic Flow
policy. The coordinator requests a logical role, not a provider. Explicit role
profiles win; otherwise the existing administrator candidate catalog, role tier,
and local-first provider order determine the binding. Worker factories cannot
accept model/provider overrides or delegate through Flow. The checked task tool
rejects names outside its roster, including unrelated SDK registry entries.

Built-in profiles and implementation defaults require no handwritten runtime.toml.
Existing default, stage, role and profile settings remain authoritative; an old
native coordinator setting fails with instructions to bind it to worker roles.
A deliberately selected compatible local SDK coordinator remains supported.
An explicit coordinator profile does not override every worker's provider.

Inspect `flow workflow runtime --json` for configuration and subscription readiness.
OpenHands requires a separate human subscription sign-in; native CLI login does
not satisfy it. Follow `docs/openhands-policy-routing.md`. Do not initiate login,
copy credentials, approve consent or use API billing on the user's behalf.
Missing sign-in or a required human terminal fails before stage entry.

SDK task calls require explicit host confirmation through the existing
`--confirm-pending` / `--reject-pending` workflow. Native worker permission requests
also require human terminal choices, unless an existing explicit legacy permission
setting applies. Do not auto-confirm either layer. Native workers retain their
native tool permissions; no OS sandbox or shell-launch prohibition is implied.

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
