# flow

Portable AI workflow framework.

## Layout

- `cli/` - local CLI entrypoint
- `templates/` - repo scaffold source
- `hooks/` - reusable hook scripts
- `scripts/` - setup helpers

## Local install

```bash
./install-flow.sh
```

This installs a `flow` launcher at `~/.local/bin/flow` and links the framework
repo into `~/.flow/framework`.

## First commands

```bash
flow doctor
flow setup machine
flow setup project
```
