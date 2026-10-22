# Goose authentication and an approved provider pool

This candidate keeps Goose as the worker dispatcher. LangGraph retains approval, durable execution state, independent checks and review acceptance. It does not activate or migrate the installed release.

## Separate authentication routes

The default `chatgpt_codex` coordinator uses Goose's OAuth cache at `$GOOSE_PATH_ROOT/config/chatgpt_codex/tokens.json`. Native `codex-acp` uses the existing native Codex login. Native `claude-acp` uses Flow's private Claude configuration and the real user HOME for keychain discovery. Ollama uses its explicitly configured loopback endpoint and already-installed local models. Native Claude is not the Anthropic API-key provider.

Goose readiness checks its own owner-only, structurally valid cache and recorded expiry; native Codex login is never accepted as proof of Goose authentication. Expired access with an existing refresh token is left to the provider’s normal noninteractive refresh at dispatch, not treated as a demand to sign in again. This local observation does not prove remote authorization, quota or model availability. Flow sets `GOOSE_CHATGPT_CODEX_NONINTERACTIVE=1`: missing credentials or failed refresh return an error instead of starting browser OAuth. A failed unattended refresh preserves the existing credential file. Interactive upstream configuration remains an explicit, separate user operation.

The supported installed setup command is:

```sh
GOOSE_PATH_ROOT="$HOME/.flow/v2/state/goose-home" \
GOOSE_DISABLE_KEYRING=1 GOOSE_TELEMETRY_ENABLED=false \
"$HOME/.flow/v2/current/v2/runtime/bundled-goose/goose" configure
```

Choose ChatGPT Codex and complete the browser sign-in. Configure may also write Goose provider/model settings and test the connection. It is not an auth-only command. The stable absolute Goose root persists across per-run HOME directories. Never copy native credentials into this cache.

## Explicit authorization to choose workers

A new work item may freeze a pool of existing named runtime profiles. The command below requires this candidate or a future release containing it; installed v0.53.0 does not have --implementation-pool. The tested fixture explicitly selected native models in its project profiles (pool-codex: codex / gpt-5.6-sol; pool-claude: claude / sonnet); production native profile settings were preserved:

```sh
flow --project /absolute/project --work example create \
  --brief-file /absolute/brief.json \
  --implementation-pool pool-codex pool-claude local-correctness local-fast
```

The profile names must exist. Creation resolves their exact provider/model settings and installed local model digests. The entire pool participates in the existing immutable approval snapshot. This is mutually exclusive with `--implementation-profile`. Existing single-profile work remains single-profile and cannot acquire a pool by resume or configuration edits.

Goose chooses an `implement-<profile>` recipe through its existing Summon delegate tool, rather than a Flow-written model router. Each attempt-local recipe fixes the approved provider/model and task defaults. Pool dispatch rejects provider/model, extension, working-directory, sampling and bound-parameter overrides. The resolved recipe must be the exact frozen file, preventing a same-name workspace recipe from shadowing it. The operator binds each allowed recipe’s byte length and SHA-256 outside model-writable files; dispatch verifies a single read and parses that same buffer, rejecting in-place modifications. Readiness checks use the operation’s actual source allowlist, so independent review does not require unused implementation providers. Extra instructions may clarify the approved assignment without replacing the frozen task.

Local members currently share one explicit endpoint/context/output/compaction configuration; incompatible transport settings fail before execution. Different local model digests remain independently frozen and checked. No model is pulled during readiness or delivery. The supported pool coordinator is Goose directly; a native ACP coordinator with a pool fails explicitly instead of silently becoming a fixed-profile run.

The quality-reviewer is advertised and callable for optional implementation-stage inspection. The required final independent reviewer remains the separately configured quality-reviewer in a fresh session; an earlier inspection never substitutes for that final review. Review and independent deterministic checks remain required. Native ACP recipes carry the actual assignment and response schema in the user prompt because ACP does not consume Goose's system prompt. Native sandbox rules are unchanged.

## Evidence boundaries

Distinguish provider readiness, the coordinator's selected source, a real child provider/model session, worker execution, result consumption, independent tests, review, and actual knowledge retrieval. A singleton-pool route test proves dispatch coverage, not autonomous selection. One successful small fixture does not establish model-selection quality or broad reliability. The native ACP alternative remains available for explicitly selected single-profile work.
