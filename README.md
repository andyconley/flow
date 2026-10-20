# Flow

Flow v2 uses Goose and LangGraph to coordinate definition, solution, planning,
implementation and review. Your native Claude/Codex host handles conversation
and human decisions. It does not become the researcher, specialist dispatcher
or implementation coordinator.

## Install or migrate once

Supported production target: **Apple Silicon macOS 15+**, **Python 3.12** and
**Node.js 24/npm**. Other targets are not release-qualified. Ordinary users need
no Rust toolchain or local Goose build.

```sh
curl -fsSL https://raw.githubusercontent.com/andyconley/flow/main/install.sh | bash
flow --version
flow doctor --json
```

Existing legacy/source-bound users must run that bootstrap **once**, after
finishing active Flow operations. The old updater is not the migration path.
The bootstrap installs the published v2 release and makes `flow` select it.
There is no supported legacy install/update mode, `--develop` mode, or silent
OpenHands fallback. Old code, user configuration, user commands and history are
preserved; ambiguous ownership or edited managed surfaces block migration.

## Update and recover

```sh
flow update --check --json
flow update
flow rollback
```

Normal updates fetch the published release manifest, code, hashed Python wheels
and patched Goose assets. Node dependencies use npm ci and package-lock
integrity. Every downloaded asset is checked before activation. Code and Python
environments live in versioned directories under `~/.flow/v2/releases/`;
launchers select `~/.flow/v2/current`. Deleting your original checkout is safe.
Mutable state stays under `~/.flow/v2/state/`. Updates refuse active operations.
Rollback restores the prior selection and native surfaces, preserving history;
post-install user edits must be reconciled instead of overwritten.

[Installation, one-time migration and rollback](v2/FLOW_V2_INSTALL.md)

## Work through the stages

```sh
flow --project /absolute/project --work example create --request 'Investigate this change'
flow --project /absolute/project --work example assign --stage define --question 'Clarify needs and acceptance criteria'
flow --project /absolute/project --work example status
# After the human authorizes the exact assignment revision:
flow --project /absolute/project --work example run-stage --stage define --revision ASSIGNMENT_REVISION --actor Andy
```

Goose coordinates specialists and returns a persisted stage artifact. Present
that result conversationally; record a human stage decision against its exact
revision. Repeat for solution and plan as needed. The plan coordinator can
propose a complete brief, but only a separate exact-revision human approval
starts implementation. Checks and fresh review remain graph-owned. Research
that changes the project candidate is blocked for scope review.

Permission and uncertain-effect pauses never authorize automatic replay.
Historical migrated work remains readable; create a fresh successor rather
than importing old approval into new execution. Existing project partial edits
are not reset. No login, provider inference, deployment or security-setting
change occurs during installation or release verification.

[Workflow contracts](v2/GLG_WORKFLOWS.md) · [Operations/history](v2/FLOW_V2_OPERATIONS.md)

## Release production

Release CI builds the exact Goose upstream commit plus deterministic full-index
Flow patch with Rust 1.99.0 and locked Cargo dependencies, and records source,
patch, binary, architecture, deployment target and checksum provenance. The
release gate exercises the actual distribution in disposable homes, including
migration, failed updates, rollback, stage dispatch and native-surface ownership.
Publication requires exact source/plan/evidence identities and all gates passing.
Public release assets and consumer updates are checked after publication.
Live Claude/Codex delivery qualification is separate from these offline checks.

This breaking v2-only cutover follows the repository's pre-1.0 version policy:
a breaking Conventional Commit advances the minor release (expected v0.51.0).
OpenHands execution is retired from supported installation/update paths.
Historical read/report modules remain available for retained records.

## Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md), [security policy](SECURITY.md) and
[the release/migration design](docs/v2-managed-release.md).
