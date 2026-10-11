# Claude native acceptance preparation

No Claude model request, live ACP launch, native permission update or settings
change was made during this preparation.

## Actual authentication visibility

Official `claude auth status` reports:

| Execution context | Logged in | Authentication | Provider | Subscription |
| --- | --- | --- | --- | --- |
| Managed restricted context | false | none | firstParty | absent |
| Normally reviewed host status command | true | claude.ai | firstParty | team |

Only these flags were recorded. No token, email, account identifier or credential
file was read, exported or copied. The existing login is available on this host;
a new login/grant should not be requested merely because the restricted status
command cannot see it. Installed official CLI: `2.1.296`.

## Smallest existing stock path

OpenHands SDK `1.54.0`; catalog adapter
`@agentclientprotocol/claude-agent-acp@0.63.0`. The published adapter pins
`@anthropic-ai/claude-agent-sdk@0.3.220`; it uses the bundled native CLI. The
installed host CLI version is not a claim about that bundled CLI's version.

Proposed disposable project:
`/Users/andyconley/Documents/Codex/2026-10-11/task-3/flow-openhands/.venv-openhands/claude-native-acceptance`.

The configuration below is a proposal only, not an enabled profile:

```toml
default_profile = "claude-acceptance"
[profiles.claude-acceptance]
kind = "claude"
session_mode = "default"
# Enable only after the actual scope below is approved:
# permission_requests = "stock-openhands"
```

Reuse existing authentication in place: `acp_isolate_data_dir=false`,
`acp_file_secrets=[]`; no API credentials/routing override. Stock SDK owns the
bridge, tools and resume. Use the native default/catalog rather than inventing
an API model route. Provision the pinned official package/dependencies into the
disposable project's SDK npm cache through normal review if required.

The acceptance task would read a small fixture, produce requirements and
acceptance-criteria artifacts, then resume the same session to confirm them.
No implementation, source checkout, live install or Witmark edits are intended.

## Permission effects: what can and cannot be isolated

Stock OpenHands chooses the first permission option. Ordinary pinned Claude
requests put `allow_always` first, followed by one-time allow. The adapter returns
native `suggestions` unchanged when present; without suggestions, it adds a
rule for the tool with `destination="session"`. That fallback is session-scoped,
but may be tool-wide rather than limited to one command/file. It is incorrect to
call every allow-always permanent. It is equally incorrect to guarantee that all
updates expire: suggestions can persist user/project/local permission rules.
ExitPlanMode can offer an automatic mode transition first.

The adapter supports richer SDK settings/tools in ACP `_meta.claudeCode.options`.
The installed stock OpenHands ACPAgent exposes no general session-options/meta
field or public permission-option/suggestion-selection callback. Its existing
model metadata path does not provide that configuration surface. Therefore the
current stock path cannot force every suggestion's destination to `session` or
select the one-time option, and Flow has not patched private callbacks, created
a replacement transport or added a custom approval/file-control layer.

`default` prevents selecting initial `bypassPermissions`; it is not a promise
that automatic permission suggestions cannot broaden native tool permissions.
The acceptance prompt can request no ExitPlanMode or external edits, but intent
is not enforced containment.

## Actual containment available

The managed outer sandbox is enforced for normal commands, with restricted
filesystem writes and network. Authentication was not visible through the normal
restricted official status check. There is no additional narrow keychain/native
home grant mechanism in the execution tool, only the existing sandbox or normally
reviewed unsandboxed execution.

Visible user settings have `permissions.defaultMode="auto"`, no explicit
`sandbox.enabled`, and an existing filesystem write addition for `//opt/homebrew`.
No worktree Claude settings file or managed-settings file was found at the two
standard inspected locations. None were changed. This is not exhaustive proof
about every enterprise policy source; it does establish that independent Claude
workspace/tool containment has **not** been verified here. In particular,
`default` mode alone is not equivalent to Codex's `agent` filesystem sandbox.

Running outside the outer sandbox would expose the ordinary host access of the
native launcher/tools, subject to Claude's automatically answered permission
system. The present stock configuration cannot honestly promise that those tool
writes are enforced to stay within the fixture project or that global native
permission settings can never change.

## One concrete approval question

**Do you approve one Claude-only fixture acceptance and same-session resume in
`.venv-openhands/claude-native-acceptance`, using your existing first-party Team
login and stock OpenHands `default` mode, through a normally reviewed run outside
the outer sandbox, including native cache/session/history/auth-refresh traffic
and automatic permission answers that may create session tool-wide grants or
persist user/project permission rules? This path has no verified independent
workspace/tool confinement and can expose ordinary host access; it excludes
explicit bypass mode, credential copying, paid API routing, deployment and edits
to the original Flow/Witmark code or installed Flow.**

This is a materially broader Claude permission scope than the completed Codex
acceptance. Its foreseeable native bookkeeping paths include the existing Claude
home's projects/sessions, debug/cache state and `.claude.json`; persistent
suggestions may touch user `.claude/settings.json` or project/local settings.
Normal native token refresh may use the existing official credential backend;
no credential export, new login or new account grant is proposed.

If persistent rule updates or unconfined native tools are unacceptable, the
current host configuration is not ready for that acceptance. An independently
enforced, already authenticated stock workspace would be needed first. This memo
does not invent one, silently enable a sandbox or claim project intent enforces
access. The question above is approval for the actual known stock path, not an
assertion that session-only containment exists.
