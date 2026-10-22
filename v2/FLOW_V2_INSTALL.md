# Managed v2 installation and one-time migration

Production support is Apple Silicon macOS 15+, Python 3.12 and Node.js 24/npm.
No Windows, Linux or Intel Mac release artifact is claimed. Runtime deployment
metadata is not live provider qualification. No Rust is needed by consumers.

The installer and `flow update` require **exactly Node.js 24.x**, not 24 or newer.
They use `node` and `npm` from the invoking shell's PATH and probe both before
release discovery or managed preparation. Successful probes show versions and
paths on stderr; JSON output remains on stdout. Missing, broken or unsupported
executables produce an actionable error without changing the selected install.
Select Node 24 using your existing version manager (for example, `nvm use 24`),
or install it with your preferred installer/manager (`nvm install 24` if using
nvm). Ensure `npm --version` succeeds, then retry. Flow never installs or switches
system Node/npm automatically. `FLOW_V2_NODE` does not override this prerequisite
check. The one-time bootstrap fetches metadata and a temporary tagged checkout
before this check; `flow rollback` bypasses it.

## Existing legacy/source-bound installations

Finish active operations, retain partial edits, and run once:

```sh
curl -fsSL https://raw.githubusercontent.com/andyconley/flow/main/install.sh | bash
flow --version
flow doctor --json
```

Do not ask the old `flow update` to perform this breaking migration. The new
bootstrap fetches the published stable release and selects v2. `install-flow.sh`
and `install-flow-v2.sh` are aliases for this managed release installer; old
`--release`, `--develop`, side-by-side and OpenHands modes are unsupported.

Ownership manifests and hashes protect existing native surfaces. User-overlay
commands are retained, configuration edits remain selective, and unknown/edited
collisions block migration. The original `.flow/source`, `.flow/user`, runtime
stores and project history remain in place. Existing source-bound v2 artifacts
are copied into managed history without copying credential files; they are
read-only for workflow mutation. Use `create --legacy-run ID` where applicable
or create a distinct successor after inspecting the preserved evidence and
quiescence. Prior approvals are never new execution authority.

## Active identity and retained legacy state

```sh
flow --version
flow installation status --json
flow doctor --json
```

`flow installation status` is a read-only, offline installation check requiring
no work ID, Node probe, knowledge reconciliation or provider login. It reports
`mode`, selected `version`, `source_sha`, runtime/code paths and the authoritative
`~/.flow/v2/current` pointer. `invocation` distinguishes the code being executed
from the selected install: a source checkout or an older unselected release is
not presented as active. `flow --project PROJECT --work ID status` is work-item
status and includes an `installation` object; it is not the installation command.

An old `[install].version` (for example `v0.49.1`) in `~/.flow/config.toml` is
labeled **legacy v1, not authoritative for v2**. A real `~/.flow/source` release
directory is likewise retained legacy state, not the selected v2 source. These
files are not rewritten, relinked or deleted merely to make their versions look
current: they may be needed when rolling back to a pre-v2 installation. The rollback result reports the restored pointer's manifest rather than the
last install receipt or old TOML. Restoring an older release may also restore
a CLI that predates `flow installation status`; use `flow --version` then, and
retain the rollback JSON as the selection record. If rollback restores pre-v2
state, that result explicitly reports no managed release; it does not invent a
v2 version from legacy fields. The restored pre-v2 CLI may lack the new command.
A broken pointer or invalid manifest is reported as invalid selection without a
legacy-version fallback.

A separate clone such as `~/personal/flow` is not an installer input. Run
`flow update` from any working directory; no `git pull`, stash, reset or checkout
cleanup is needed. Release updates leave staged, unstaged and untracked clone
files alone. Use the selected code path in status to locate the running release;
use Git separately only when intentionally maintaining that independent clone.

Install/update/check/rollback results include `installation` identity. In
`update --check`, `latest` and its `source_sha` describe the available target;
`installation.version` and `installation.source_sha` describe what is selected
now. Check-only output explicitly says no activation occurred. Human
summaries on stderr label selected mode/source and retained legacy fields.
Preparation and knowledge-worker logs go to stderr; stdout remains one JSON
result, including with `--json`. Failed updates report the still-selected runtime.

## Stable layout and updates

- `~/.flow/v2/releases/TAG-SHA-ID/`: immutable release code and its own Python/npm dependencies.
- `~/.flow/v2/current`: atomic selected-release pointer.
- `~/.flow/v2/state/`: shared workflow artifacts, sessions and native-client-owned state.
- `~/.flow/v2/backups/`: native-surface snapshots for rollback.
- `~/.local/bin/flow` and `flow-v2`: stable launchers; no reference to the bootstrap checkout.

`flow update --check --json` inspects the latest published release. `flow update`
fetches and verifies release code, hashed Python wheel closure and the patched
Goose bundle, then installs npm dependencies with lockfile integrity. Preparation
happens before selection. Failed downloads/dependencies preserve the active
release. The installer refuses active/unreconciled processes. `flow rollback`
restores the previous selection/surfaces; it refuses post-update user edits
instead of overwriting them. First-install rollback restores the saved prior
installation as recovery, not a supported legacy execution/update mode.

If GitHub limits release metadata requests, the updater prints the HTTP status,
remaining quota, reset time and retry decision on stderr. It honors `Retry-After`
and exhausted-quota `X-RateLimit-Reset` headers, with at most four attempts and
five minutes of total waiting per metadata request. A later reset fails with its
time visible; retries never run early to fit the budget. Maintainers can set
`FLOW_GITHUB_RETRY_WAIT_SECONDS` from `0` to `3900`; hosted release verification
allows one full hourly reset. Metadata errors never print tokens or response
bodies. Public consumer checks stay anonymous and still must pass.

Installation/update does not start coding/review-provider inference, account login
or a live agent smoke run. Knowledge provisioning may run the already selected
local extraction model and build a new audited generation when its pipeline
fingerprint changes, even while reusing downloaded assets. Authored notes and
settings are preserved; generated snapshot selection can advance after audit. Native clients own sign-in; any later worker auth pause is separate from
release readiness. After updating, open a fresh native host session to refresh
skills. The host delegates all stage coordination through the CLI graph; it does
not research or plan the work itself.

## Stage commands

Use `flow --project PROJECT --work ID` as the prefix. `create` and `assign` write
proposals only. Human authorization of an exact assignment is
`run-stage --stage define|solution|plan --revision REVISION --actor ACTOR`.
Goose/LangGraph dispatches specialists and persists the result. A human stage
approval uses `approve-stage --stage STAGE --revision RESULT_REVISION --actor ACTOR`.
Only `approve --revision BRIEF_REVISION --actor ACTOR` starts implementation.
Status remains read-only during delivery; permission/uncertainty requires an
explicit decision rather than automatic retries. `stage --file` records supplied
human notes; it is not an alternative host research/execution path.

## Maintainer package testing

CI produces `flow-code.tar.gz`, `python-wheels.tar.gz`, `goose-macos-arm64.gz`,
Goose provenance JSON, `release-manifest.json` and SHA256SUMS. An explicitly
selected local copy of those verified assets can be installed with
`PYTHONPATH=v2 python3.12 -m poc.managed install --bundle /absolute/assets`.
This is an offline package-consumer path, not a source-bound installation.
Only maintainer build tooling compiles Rust. Production publication rejects the
existing-binary shortcut used for offline packaging experiments.
