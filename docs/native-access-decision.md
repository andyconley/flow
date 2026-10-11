# Native ACP access decision

Native automation is implemented using stock `ACPAgent`, but live native
acceptance is **incomplete**. Interactive handoff is a temporary fallback, not
the final architecture. This document records the actual decision needed before
running a native subscription session from this environment.

## Verified versions and behavior

- OpenHands SDK `1.54.0` installed from PyPI.
- Its official npm catalog pins `@agentclientprotocol/codex-acp@1.10.0` and
  `@agentclientprotocol/claude-agent-acp@0.63.0`.
- The exact registry tarballs were inspected without launching native agents.
- Flow sets Codex `acp_session_mode="agent"`. The pinned adapter maps it to
  `workspaceWrite`, `networkAccess=false`, `approvalPolicy=on-request`,
  `approvalsReviewer=auto_review`, no additional writable roots, and ordinary
  temporary directory access. It does not select `agent-full-access`.
- Flow sets Claude `acp_session_mode="default"`, not `bypassPermissions`.
- OpenHands' stock permission callback chooses the **first** offered option.
  In the pinned Claude bridge, an ordinary tool permission request offers
  `allow_always` first. That returns the native SDK's permission suggestions or
  adds a tool allow rule with `destination="session"`. ExitPlanMode can offer
  an `auto` mode change first. Native suggestions may target other native
  permission settings; the initial mode alone does not stop these updates.
- Codex ACP also handles requests for additional sandbox permissions. Stock
  OpenHands answers them automatically; only the independently enforced outer
  execution containment can prevent an actual access expansion.

These are concrete native grant implications, not an architectural preference
for retaining Flow's old controls. Flow does not patch the SDK callback, build an
ACP transport, or recreate its old approval/dispatch machinery.

## Current containment and login observations

The execution environment grants read access to the filesystem and write access
only to this task's workspace and temporary directories. Network is restricted.
SDK/native children inherit that containment when launched through ordinary
sandboxed execution. Elevating the whole Python/native process would remove
that boundary and is **not** an equivalent scoped approval.

The existing Codex saved login reports `auth_mode=chatgpt`, subscription tokens
present, and no saved API key. Values were not printed, copied or modified.
The user Codex config says `danger-full-access`/`approval_policy=never`; Flow
explicitly selects the narrower stock ACP `agent` mode instead.

Installed Claude Code is `2.1.296`. A harmless `claude auth status` in this
restricted environment reported `loggedIn=false`, `authMethod=none` and
`apiProvider=firstParty`. This does not prove that another host/session lacks a
subscription; it means a login is not visible to this execution environment.
The current Claude default permission mode is `auto`. Flow selects `default`.
No native login, token export or credential copying was attempted.

## Exact choice to present once

**Approve stock OpenHands native ACP permission handling within an independently
confined execution environment, or keep live native execution pending?**

Approval would cover the SDK's automatic native permission answers, including
possible `allow_always` rules and session mode changes **only for the isolated
Flow implementation sessions**. The enforceable outer scope must still be:

1. Product/code writes restricted to the selected new isolated worktree and its
   `.flow/runs` storage; original Flow source, installed `.flow/source`, Witmark
   worktrees and the preserved candidate patch stay excluded from writes.
2. Existing native account authentication through the official native agent.
   No API keys, credential copies, forwarded secret blobs or new account grants.
3. Explicit native state writes needed by that account: Codex session/history/log
   state under the existing Codex home; Claude project/session/debug state under
   its existing native home. Additional state paths and token-refresh writes
   must be identified from the actual native startup diagnostic before granting
   them. Global native permission/settings files must remain outside write
   scope unless separately approved. The current environment does not grant
   these writes.
4. Outbound subscription inference/authentication services for the selected
   native provider. Exact domains must come from the official native runtime's
   startup/network policy; this task does not add blanket network access or
   silently route to paid APIs.
5. If Claude needs login visibility, use the user's existing official native
   login on the intended host. Creating or copying credentials is outside this
   task; the user must resolve a genuinely absent official login.

If this environment cannot enforce that scoped containment, select an existing
OpenHands workspace that can enforce it and has authorized native login access.
Do not replace it with an unrestricted elevated local process.

After approval and containment are established, set
`permission_requests="stock-openhands"` in the approved native runtime profile.
The adapter is already implemented; that setting acknowledges the concrete
native permission behavior. It is not an OS grant or proof of confinement.
Neither the setting nor any extra host/network grant has been enabled in this
branch's default configuration.

## Verification completed independently

The real SDK runs local coding conversations/tools and persists/resumes sessions.
A deterministic ACP protocol peer tests the real stock SDK transport, explicit
Codex/Claude modes, permission callback and resume in disposable directories.
That test does not use real native credentials or constitute live native
subscription acceptance. A real native stage remains pending the access decision.
