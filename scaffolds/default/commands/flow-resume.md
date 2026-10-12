# flow-resume

Inspect `flow workflow status <work-id>` and `flow run history <work-id>`. For a
paused or blocked workflow, resolve the recorded issue and use the legal Flow
`resume` transition. Continue the stage with `flow workflow execute <work-id>
--stage <stage> --task-file <task.md>`; OpenHands restores its own conversation.

Do not reconstruct SDK history in a Flow execution ledger. A changed profile,
role or workspace needs `--new-session`, preserving previous SDK sessions.
For native profiles, prepare `flow workflow native-handoff` and continue in the
existing official agent session with its current account and permissions.

Historical MAF runs remain inspectable and are not resumed by this branch. Start
a new workflow referencing useful prior artifacts. Do not cancel, migrate or
alter an existing provider run merely to adopt this runtime.

Use the active runtime memory provider as companion context when available.
Verify material claims against canonical project artifacts and code.
