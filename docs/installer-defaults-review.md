# Reviewing defaults during installation

Install and update invoke the activated source's defaults review before adapter
synchronization. The review is authoritative by default: every setting that
still differs from (or masks, see below) the incoming default is removed from
the overlay so that scope inherits it. There is no interactive Keep/Adopt
question, and no distinction between a TTY and a script — `flow defaults-review`
behaves the same way whether a human is watching or not. `flow defaults-review
--check` reports the same pending differences without reading stdin or writing
anything; use it to preview before an install or update, or in CI. Review/apply
failure stops adapter synchronization while leaving the installed source
available to repair.

Use `flow defaults-review --incoming /path/to/scaffolds/default/flow.toml` to
review a specific incoming release. User scope is `~/.flow/user`; `--user-overlay`
selects an isolated alternative. `flow install` and `flow update` always review
the current project automatically when the command runs from inside one with
its own `.flow` (found by walking up from the working directory, the same way
`flow doctor` locates a project root) — `--project /path/to/project`
(forwarded by `flow update --project PATH` and `flow install --project PATH`)
only ever adds further, explicitly named scopes on top of that one; it never
replaces the automatic inclusion. There is still no canonical project
inventory or filesystem-wide search beyond the project you are standing in.
`flow defaults-review` run directly does none of this cwd detection by
default — only explicitly named `--project` scopes are ever reviewed — unless
`--auto-project` is given, which applies the exact same current-project rule
(and the same `~/.flow` exclusion). `install-flow.sh` passes `--auto-project`
so the shell bootstrap installer gets this inclusion too, without
re-implementing the walk-up/exclusion logic in bash. An absent override file (no
local overrides at all, or the common case of no runtime.toml) is reported
and skipped without affecting the exit code. A file that exists but cannot be
read or parsed is also skipped, but the run exits 1 and prints that the reset
is incomplete rather than claiming success — the same applies when a setting
could not be safely separated from its surrounding TOML (`adoption_unavailable`).
Reports identify the file, scope, local and incoming values, inheritance after
removal, and masks in selected projects. Only flow.toml and recognized
runtime.toml routing/model and permission overrides are considered — a
`default_profile`/stage profile pin is reviewable whether it names a native
(claude/codex) or local (ollama) profile, since the built-in default needs no
pin at all either way; only a profile's own connection fields (model,
base_url, context) are preserved as machine data. Machine endpoints, installed
models, context, credentials and instructions are not reset, because they are
never part of the incoming defaults being compared against.

Adopting removes the override; it never writes a copied default. Removal
applies even when a local value is already byte-identical to the incoming
default, for settings whose mere presence changes behavior (`MASKING_PATHS` in
`cli/defaults_review.py`; provider_order is the current example — an explicit
order that merely restates the framework's own order still suppresses
role-specific hosted-provider preferences by being present at all, so leaving
it in place would keep masking preferences no install ever intended to
override). If a setting cannot be safely separated from the surrounding TOML,
the report records that concrete exception (`adoption_unavailable`) instead of
claiming the reset succeeded. Candidate catalogs replace arrays. A complete
catalog can be removed after explicit selection; removing one entry from a
remaining array cannot expose inheritance and is refused. Duplicate IDs,
unsupported multiline/quoted assignment forms and semantic changes beyond the
selected removal require manual editing. Unrelated bytes, line endings,
ordering and comments are preserved.

Selected files are parsed and their effective policy validated before writes.
Original bytes are backed up in a private `defaults-review/<transaction>/` folder
under the user overlay. Hashes are rechecked before atomic per-file replacement.
This is a recoverable multi-file operation, not one filesystem transaction.
On failure, matching applied files are restored; subsequent edits are preserved
and reported as partial recovery. Backups and the recovery receipt remain
available. Run `flow defaults-review --recover /path/to/receipt.json` to retry
recovery. Recovery from a run's own backup is the explicit opt-out for that
run's result — there is no separate flag to keep an individual setting, since
the default behavior is to adopt everything that differs or masks. After
repair, rerun review, then `flow sync <target> --user` for the affected
adapters.

Native model pins inherit role-dependent models, so their report lists models by
role. Removing a role profile pin exposes the eligible provider roster; the SDK
coordinator chooses a qualified target, while role-only calls follow inherited
preferences. Runtime permission overrides are reviewable individually and are
removed by default like any other override, reverting a profile to stock
automatic SDK permission handling unless re-added explicitly after the run.
Automatic SDK dispatch and stock native permission handling do not change
lifecycle approval gates, authentication, or the actual outer filesystem/network
containment.

An install/update that resumes an existing OpenHands SDK conversation also
re-asserts the current confirmation default (NeverConfirm unless the active
workspace explicitly sets `confirmation = "always"`) rather than trusting a
resumed conversation's own persisted policy, since a conversation created under
an older binding can still carry a stale `AlwaysConfirm` policy in its
serialized state. A brand-new conversation already starts from the SDK's own
default and needs no extra reset.
