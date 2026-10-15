# flow-review

Review the implemented change against requirements and acceptance criteria. Record actionable findings, validation results and a supported acceptance recommendation.

Flow owns this workflow stage and its outputs. OpenHands owns execution, tools,
conversation history, retries and specialist delegation. Do not rebuild a Flow
manager, file broker, provider loop, token/rate gate or execution ledger.

## Enter and execute

For a configured self-hosted profile:

```sh
flow workflow execute <work-id> --stage review --task-file <task.md>
```

The command enters a legal stage from the prior approved state and resumes the
stage/role's SDK conversation. Use `--role` and `--profile` for a specialist or
different self-hosted endpoint. Profile and role settings live in `.flow/runtime.toml`
and the user overlay. The installed OpenHands packages must match the pinned
runtime requirements. Actual workspace permissions still apply.

For an existing official native Codex/Claude session, select `--profile codex`
or `--profile claude`. Install/update provisions these interactive profiles only
when no user runtime configuration exists; existing configuration is preserved.
Inspect `flow workflow runtime --json` for resolved roles and missing setup.
SDK readiness is not execution readiness; never bypass a missing profile by
implementing directly in the host. Native handoff uses existing permissions and
does not enable automatic ACP permission handling. `workflow execute` with a native
profile uses terminal approvals by default: run it from a human-controlled terminal;
headless execution fails closed. These are terminal prompts, not desktop dialogs.

```sh
flow workflow native-handoff <work-id> --stage review --profile <codex-or-claude-profile> --task-file <task.md>
```

Use that context artifact in the native session with its existing subscription
and permissions. Native execution uses OpenHands ACPAgent through Flow's terminal permission proxy.
Every native permission request requires explicit human selection; timeout, EOF or
missing terminal denies it. Selecting a persistent option can change native rules.
The legacy `stock-openhands` option automatically answers requests and requires
a separate access decision; it is never selected by default. Native handoff
is a temporary interactive fallback. Do not copy credentials or switch billing.

## Durable outputs

Write these files under `.flow/runs/<work-id>/`:

- `review.md`

For verification-v1 work, inspect the tested workspace, check logs and registered
evaluation input changes. Equivalent test repairs need independent before/after
evidence; changed success conditions need separate user approval in a linked
successor workflow. Do not accept assertion deletion, reduced coverage or an
implementation shortcut merely because the recorded checks pass.

Use specialist roles, project skills, context and existing approved artifacts as
needed. SDK TaskToolSet handles configured specialist delegation. Record actual
results and unresolved questions; a model response alone does not approve work.

## Approval and continuation

After the user/operator has reviewed the outputs:

```sh
flow workflow approve <work-id> --stage review
```

If findings require changes, use `flow run transition <work-id> request-refinement`,
then continue implementation. Accepted review can proceed to `flow-archive`.

Inspect progress with `flow workflow status`, `flow run history` and SDK outcome
artifacts. Pause/block/resume through ordinary Flow lifecycle transitions.

Use the active runtime memory provider as companion context when available.
Verify material claims against canonical project artifacts and code.

Follow `standards/git-commits.md` for any authorized commits.

Verification-v1 output contract: write exactly one `Verdict: ACCEPT` or
`Verdict: REJECT` in `review.md`. For changed registered tests, separately write
`Test equivalence: EQUIVALENT`, `MATERIAL` or `UNCERTAIN` and before/after rationale.
An import spelling repair can preserve assertions; correcting implementation
logic to meet those assertions is not a criterion change. A passing sample does
not justify assertion deletion or a semantic shortcut. Missing or unusable review
output requires host-allocated `workflow repair --check-id review-output` within
the persistent two-repair limit and shared deadline. Do not synthesize approval.
