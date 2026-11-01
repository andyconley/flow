# Codex and Claude subscription-only setup

Flow can enforce a machine-owned policy that permits only Codex and Claude
subscription workers. LangGraph still coordinates the workflow and Goose still
runs its agent/tool layer. Dormant local-provider adapters remain installed.

Merge these settings into `~/.flow/user/runtime.toml` on each machine:

```toml
default_profile = "codex"

[execution_policy]
native_only = true

[profiles.codex]
kind = "codex"
session_mode = "agent"

[profiles.claude]
kind = "claude"
session_mode = "default"

[roles.lead-developer]
profile = "codex"

[roles.quality-reviewer]
profile = "claude"
```

Retain any native model/session settings you already use. Remove obsolete local
profile bindings from the user configuration. Optionally set
`provider_order = ["codex", "claude"]` in the `[provider_selection]` table of
`~/.flow/user/flow.toml`. The machine policy enforces the ceiling independently
of project configuration, frozen worker pools, and provider ordering. An old work
item containing a local worker must be recreated with native workers; Flow will
refuse to submit the old selection. Explicitly local Codex provider configurations
are also rejected. The policy never enables API-billed providers or copies auth.

## Authentication

Flow uses the existing native client authentication paths. Claude's managed
private profile is `~/.flow/v2/state/claude-home`. To sign into that profile with
a Claude subscription, run the installed Claude executable interactively:

```sh
CLAUDE_CONFIG_DIR="$HOME/.flow/v2/state/claude-home" \
  "$HOME/.local/bin/claude" auth login --claudeai
```

Use the actual Claude executable on your PATH if yours is installed elsewhere.
Do not select `--console`, which uses API billing. Account-status checks do not
prove remote token validity: a revoked token can still require interactive sign-in
when a real request returns 401. Flow never initiates that sign-in itself.

## Knowledge without local inference

With the policy enabled, relationship enrichment uses one bounded, schema-constrained
Codex subscription CLI call, in the native worker sandbox. Tools and project
instructions are disabled for that call. Card prose is treated as untrusted data.
Exact source/target quotations and IDs are checked before any proposed edge is
accepted. Receipts include prompt/response digests and accepted/rejected suggestions.
A failed call or audit keeps the previous snapshot selected; there is no automatic
provider fallback. Input is limited to 180 KB and the request has a 180-second bound.

Basic Memory ingestion and full-text indexing continue without embeddings or
reranking. Keyword search and graph traversal remain available. Hybrid search
explicitly reports text-only results; vector search returns a clear unsupported-mode
error. Subscription CLIs do not replace vector embedding APIs.

Existing authored notes and published snapshots are retained. A code-only rebuild
can reuse the validated enrichment cache. No Ollama process, model download, local
model identity probe or embedding-cache acquisition is required for this mode.
The pinned Basic Memory Python runtime must already be available; a fresh machine
without it can explicitly defer knowledge with `--knowledge defer`. That deferral
is visible and does not claim knowledge readiness.

For an existing configured installation, update and rebuild with:

```sh
flow update --knowledge offline
flow knowledge process
flow knowledge status
```

The update retains machine/user settings and uses the published, verified release.
`flow knowledge status` reports `ingestion: lexical`, `search: text`,
`semantic_search: disabled`, and `enrichment: codex-subscription`. The initial
specialist expertise search requirement still applies to these indexed text results.

This setting does not uninstall Ollama, delete models, alter unrelated services,
or change device access permissions. Upgrades containing this policy implementation
preserve the constraint through the existing user overlay.
