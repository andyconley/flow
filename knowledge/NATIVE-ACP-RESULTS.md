# Native ACP knowledge-use qualification

The previously blocked **read-only production knowledge-use task now passes** in
one explicitly identified local configuration. This supersedes the blocked gate
in `ACP-STATUS.md` for this configuration only; earlier failures remain preserved.
No merge/release or active installation change was performed.

## Root causes and corrections

1. ACP clients filter inherited environment variables and execute MCP commands
   inside their native worker sandbox. The absolute-path read-only launcher and
   explicit code/knowledge/cache read grants fixed startup. Writes remain in
   per-run scratch, outside maintained notes.
2. Codex CLI 0.163.0 emits MCP tools inside Responses `namespace` objects. Ollama
   0.32.1's `ResponsesTool` request struct has no nested `tools` field; its converter
   therefore cannot transmit those nested functions to its model. Registration
   reached Codex, but definitions were lost at that provider boundary. Confirmed
   against the exact upstream release source:
   https://raw.githubusercontent.com/ollama/ollama/v0.32.1/openai/responses.go
3. The explicit local namespace adapter preserves each registered function schema,
   arguments and call ID, flattens only wire identities, and restores structural
   namespace/name fields in responses and streaming events. It replays tool
   history consistently and refuses collisions, unknown calls and unsupported
   tool kinds. It does not run searches, invent results, or select another model.
   The restored field is part of Codex's actual function-call protocol:
   https://raw.githubusercontent.com/openai/codex/main/codex-rs/protocol/src/models.rs
4. Native ACP does not consume Goose-only recipe/system context like an ordinary
   Goose provider. Native tasks now receive the complete approved task and final
   contract in their user instruction file. Ordinary providers receive a recipe
   whose prompt also contains the approved task. Mutually exclusive CLI flags
   are not combined. Flow validates final JSON against its schema independently;
   a zero process exit plus prose cannot become a completed task.
5. Qwen3:4b and Qwen2.5:7b negative trials remain negative. After namespace repair
   both executed actual search and graph calls, but did not reliably satisfy the
   final structured task. The qualified comparison uses local `gpt-oss:20b`, not a
   hidden switch to a hosted provider or credentials.

## Qualified configuration and evidence

- Actual path: Flow `GooseJob` -> pinned Goose -> codex-acp 2.2.2 -> Codex CLI
  0.163.0 -> explicit managed namespace adapter -> Ollama 0.32.1 -> local
  `gpt-oss:20b`, reasoning low.
- Exact model digest:
  `f38aa0c53da5f8c49d08c43a99df24ff53167fe68e24664a7777288e7656fdfe`.
  Download size 13,793,441,566 bytes; official registry manifest is saved with
  evidence. Weights stay in the isolated task model directory, outside Git.
- Completed ACP search returned the authored business-analyst evidentiary-status
  card. Completed ACP traversal returned its real `complements` support-lead
  neighbor, from the containing note in the BM relation table.
- Final output passed Flow's strict JSON schema, actual successful tool-call
  checks, exact authored quote and permalink checks for both cards, all four
  observed/inferred/assumed/decided labels, and preserved the unconfirmed
  database-overload hypothesis.
- The approved test workspace remained empty. No terminal/file/delegation action
  was needed. The private native configuration contained no `auth.json`; model
  inference stayed local. No direct MCP call or fallback retrieval was scored as
  this success.

Raw positive and negative results and managed wire identities are in `evidence/`.
The live harness is `verify_acp_read.py`. It uses the real production method,
process supervision, native sandbox, managed tool server and BM implementation.
It does not mock the provider, model, search or graph. This qualifies a read-only
knowledge-use task, not every provider/model or an entire code-changing
implementation/review workflow. Parent review is still required before release.

## Explicit operation

After ordinary local knowledge setup, set the native Codex private configuration
to an already provisioned, credential-free loopback model provider. Select the
model and reasoning supported by that provider. Then enable the wire adapter:

```sh
flow knowledge namespace-compat on
# Turn it off explicitly for a provider supporting native namespaces:
flow knowledge namespace-compat off
```

The option is separate from indexed corpus settings; toggling it backs up state
without re-extracting notes. It applies only to an explicitly configured local
Codex provider. It creates one ephemeral loopback HTTP listener for the job and
closes it afterwards; no daemon, installation, public listener or separate
retrieval service is added. Root/child role instructions, BM retrieval and graph
semantics remain unchanged. Unsupported upstream tool kinds produce errors.
The adapter disables unsupported hosted web search for this local transport.

Reproduce the qualified task with the isolated model already installed:

```sh
/path/to/knowledge-python knowledge/verify_acp_read.py --home /isolated/knowledge-home --work /new/empty/workspace --namespace-compat --model gpt-oss:20b --reasoning-effort low --output /tmp/native-acp-result.json
```

The harness requires a fresh workspace, uses task-local source runtime state,
and deliberately refuses an existing native auth file. Run it from an isolated
checkout, not an active installed account configuration. The model's local memory
needs and official setup are documented here:
https://developers.openai.com/cookbook/articles/gpt-oss/run-locally-ollama

## Final regression checks

The full isolated suite passed 196 tests (`evidence/flow-regression-qualified.log`). An additional ordinary-coordinator transport-scope regression also passed; the five contract tests are in `evidence/contract-regressions.log`. The original six raw inputs and their source files still match their initial SHA-256 hashes. Contract artifacts live in their own directory so permission-record discovery remains unambiguous.

The final real Basic Memory replay passed all 15 text/vector/hybrid requests, role filtering, graph traversal and snapshot-byte immutability (`evidence/qualified-retrieval.json`). The isolated Ollama server was stopped after verification. No action remains pending or uncertain.
