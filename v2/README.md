# Flow v2.0

Flow v2.0 uses the native host for shaping and user decisions, LangGraph for durable workflow state, and Goose for specialist execution and provider choice. It reuses the 13 converted Flow roles and existing signed-in Codex/Claude adapters. This checkout is **2.0.0-preview**, a source-bound local installation—not a published release.

## Install and select

From the canonical repository root, prepare the locked dependencies and install:

```sh
./install-flow-v2.sh prepare --build-goose
./install-flow-v2.sh install --dry-run
./install-flow-v2.sh install
~/.local/bin/flow-v2 --version
```

Default installation is opt-in: `flow-v2` plus one native-host `flow-v2` entry skill for Codex and Claude. The supported `flow-*` v2 command bodies are staged privately. Existing legacy `flow` and `flow-*` skills remain selected until an explicit cutover.

Use `$flow-v2` in Codex or `/flow-v2` in Claude and name the intended workflow. After host skill discovery refresh/new session, the entry skill loads only the relevant v2 command instructions. No duplicate `glg-*` skill set is installed.

```sh
flow-v2 --project /absolute/project context
flow-v2 --project /absolute/project --work work-id create --request 'Problem to investigate'
flow-v2 --project /absolute/project --work work-id status
```

Creating and shaping work do not start inference. Final exact-revision approval starts real delivery using the existing accounts; merge/deployment remain separate. See [the installation and command guide](FLOW_V2_INSTALL.md) and [workflow contracts](GLG_WORKFLOWS.md).

## Update, legacy cleanup and rollback

```sh
flow-v2 update --dry-run
flow-v2 update
flow-v2 inventory
flow-v2 activate --replace-legacy --dry-run
```

The explicit `activate --replace-legacy` selection backs up and replaces the global `flow` launcher/command skills, removes attributable obsolete legacy surfaces, and selectively removes owned hook/agent registrations. It preserves unrelated settings, credentials, project artifacts, historical runs and current role-composer source dependencies. Ambiguous ownership is reported; command/config collisions block cutover rather than being deleted broadly. `flow-v2 restore` rolls back the cutover from its backup. **Activation is a separate selection; normal install/update never silently selects v2 over legacy.**

## Code and verification

- `poc/glg.py`: internal CLI module (the old GLG name remains an implementation detail).
- `poc/install.py`, `legacy_install.py`: idempotent installation, inventory, explicit selection and reversible cleanup.
- `skills/flow-*/SKILL.md`: one portable set of supported native-host command instructions.
- `poc/work_lifecycle.py`, `workflow.py`: approvals, existing delivery/check/review graph and closure.
- `poc/artifacts.py`, `handoffs.py`: versioned context/brief/decision/assignment/result records and recovery.
- `role-bundle/`: 13 existing specialist agents/recipes with normal broad tools.

From `v2/`, use `.venv/bin/python -m unittest discover -s tests -v` after preparation. The cancellation test needs normal macOS process-list access to inspect only its own child processes. Installer tests use disposable homes and check real launcher execution, command mapping, old-to-v2 cleanup, idempotence, rollback and a pre-approval smoke without provider calls.

The local implementation was exercised with existing native accounts before integration. No private execution records or machine-specific scenarios are distributed here. The shipped offline suite tests workflow, recovery, source locks, roles and installer behavior. See [native permission propagation](GLG_NATIVE_ERRORS.md). Goose is the pinned official v1.55.0 base plus the required [integration patch](vendor/README.md), built under ignored runtime/goose rather than fetched from an unpublished fork.

The preview does not migrate active legacy runs, create credentials, alter global security settings or deploy applications. Existing account adapters remain client-owned.
