---
name: flow-resume
description: Continue a persisted workflow or inspect a permission/scope/recovery pause.
---

<!-- Managed by Flow v2.0; edit source, then publish/update the managed release. -->

This is Flow v2.0, powered by Goose/LangGraph. Use the installed v2 launcher `FLOW_V2`; shell commands and native skills are different surfaces. Replace PROJECT, ID, FILE and ACTOR with actual values. For work-item commands the full prefix is `FLOW_V2 --project PROJECT --work ID`; append the subcommand shown below. Read exact controlled references and preserve revision history. Existing native-host permissions, external-action approvals, account sessions and broad normal role tools apply. No new credentials or global security settings. Preserve Flow v1 and historical .flow artifacts; do not migrate active v1 work. Goose/LangGraph owns coordination and specialist dispatch across all stages. The host only handles conversation and human decisions.

Specialist expertise is available under `SOURCE/role-bundle/.agents/agents/` and its catalog. If a role name is not registered in the native host, request its work through the Goose/LangGraph stage coordinator; do not invent a registered agent or reinstall legacy registrations. Goose uses the existing role recipes for delivery.

Read status and exact referenced inputs before `resume`. A completed resume must not execute another worker. Use `resume --decision-file FILE` for the actual pending decision. Scope/permission decisions need action=resume|stop, actor and reason. Uncertain effects require actual inspection and actor/effect=completed|not_started/evidence, plus the recovered real result for completed. A running job stays pending; never guess not_started. Preserve the same thread and original budget. Explicit typed native boundary errors stop Goose before another dispatch. There is no automatic native session restore or job-reattach command. Changed criteria/scope needs a successor work item.

If the item is under legacy `.flow/runs`, inspect it with `status --legacy` or the read-only `run` commands. Its SDK/native checkpoint is not a v2 checkpoint. Continue through the original runtime, or create a distinct successor with `FLOW_V2 --project PROJECT --work NEW_ID create --legacy-run OLD_ID --request TEXT`. This records historical provenance and requires a new brief/approval; never replay an old approval as new implementation authority.

Before approving a successor that touches the same workspace, establish through the original runtime that legacy execution is quiescent and inspect partial effects. The handoff records quiescence as unobserved; creation is planning only. Do not claim the old process was paused/stopped or run overlapping coordinators merely because a successor exists.
