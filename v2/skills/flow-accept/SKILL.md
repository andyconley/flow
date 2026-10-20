---
name: flow-accept
description: Record the user’s separate acceptance of a reviewed-and-ready closure.
---

<!-- Managed by Flow v2.0; edit source, then publish/update the managed release. -->

This is Flow v2.0, powered by Goose/LangGraph. Use the installed v2 launcher `FLOW_V2`; shell commands and native skills are different surfaces. Replace PROJECT, ID, FILE and ACTOR with actual values. For work-item commands the full prefix is `FLOW_V2 --project PROJECT --work ID`; append the subcommand shown below. Read exact controlled references and preserve revision history. Existing native-host permissions, external-action approvals, account sessions and broad normal role tools apply. No new credentials or global security settings. Preserve Flow v1 and historical .flow artifacts; do not migrate active v1 work. Goose/LangGraph owns coordination and specialist dispatch across all stages. The host only handles conversation and human decisions.

Specialist expertise is available under `SOURCE/role-bundle/.agents/agents/` and its catalog. If a role name is not registered in the native host, request its work through the Goose/LangGraph stage coordinator; do not invent a registered agent or reinstall legacy registrations. Goose uses the existing role recipes for delivery.

Read status and the exact current closure. An explicit user request to accept that concrete result is authorization; do not ask again if it already applies. Run `accept --actor ACTOR --revision EXACT_CLOSURE_REVISION`. This creates a decision and superseding closure, preserving the prior technical closure. It is available only for reviewed-and-ready work, and does not authorize commit, merge, publish or deploy. Do not infer acceptance from successful tests or review.
