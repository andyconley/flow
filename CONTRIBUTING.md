# Contributing

`flow` is a small maintainer-led project. Contributions are welcome when they keep the framework portable, local-first, and easy to reason about.

## Before You Start

Open an issue before large behavior changes, new workflow stages, new runtime integrations, or anything that changes generated files. Small documentation fixes, tests, and narrow bug fixes can go straight to a pull request.

Good contributions usually explain:

- the problem being solved
- why it matters to Flow users
- the user-facing behavior that changes
- how the change was validated

## Local Setup

Use develop mode when working on the framework:

```bash
git clone https://github.com/andyconley/flow.git
cd flow
./install-flow.sh --develop
flow setup machine
flow setup user
```

`~/.flow/source` points at your checkout in develop mode, so framework edits take effect after the relevant sync command.

## Validation

Run the checks that match the change. For most code changes:

```bash
/opt/homebrew/bin/python3.12 -m unittest discover -s tests
git diff --check
```

When help output or generated command docs change:

```bash
/opt/homebrew/bin/python3.12 scripts/regenerate-flow-help.py --check
```

When runtime-generated surfaces change:

```bash
flow sync claude --user --check
flow sync codex --user --check
flow doctor
```

## Pull Requests

Keep pull requests focused. Include validation evidence in the PR body, and call out anything that affects install, update, sync, hooks, generated files, or local data.

Use Conventional Commits for commit messages, for example:

```text
docs: clarify release install behavior
fix: preserve user overlay files during setup
feat: add definition-stage research artifacts
```

## Generated Files

Edit the source files that Flow owns, then regenerate or resync. Do not hand-edit generated Claude or Codex runtime files as the source of truth.

Common source locations:

- `scaffolds/default/commands/`
- `scaffolds/default/agents/`
- `scaffolds/default/standards/`
- `scaffolds/default/templates/`
- `hooks/`

## Security

Do not open public issues with vulnerability details. Follow [SECURITY.md](SECURITY.md) instead.
