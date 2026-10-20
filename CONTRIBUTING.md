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

Work in a checkout without changing your active installation:

```sh
git clone https://github.com/andyconley/flow.git
cd flow
python3.12 v2/bootstrap.py prepare
```

That prepares maintainer-local test dependencies and the retained offline Goose
fixture. Normal user installation always uses verified managed releases; source
checkouts, `--develop` and legacy installation/update are not supported consumer
modes. CI builds fresh patched Goose from its pinned upstream/patch with Rust
1.99.0, packages hashed Python wheels, and verifies the real consumer bundle.
Rust is a maintainer/build-worker dependency only.

## Validation

Run the checks that match the change. For most code changes:

```bash
PYTHONPATH=v2 v2/.venv/bin/python -m unittest discover -s v2/tests -v
v2/.venv/bin/python -m unittest tests.test_release_gate tests.test_release_highlights -v
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

Release automation reads those commit messages. `feat:` produces a minor release, `fix:` produces a patch release, and before 1.0, breaking-change markers produce a minor release under release.config.cjs. `docs:` also produces a patch release. Use `docs(framework):`, `docs(commands):`, `docs(agents):`, or `docs(standards):` when a documentation change materially changes Flow behavior; those scopes produce a minor release.

The changelog is generated from commits. Put longer design context in the docs,
specs, or architecture notes changed by the work. When several commits deliver
one capability, a release-impacting commit may include one optional
`Release-Note: <text>` trailer for the concise reader-facing outcome. Keep it to
one line and 1-240 UTF-8 bytes; do not use control or bidirectional-formatting
characters, HTML comment delimiters, or a Markdown heading prefix.

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
