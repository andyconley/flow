# Applied 64K development configuration

Andy authorized the 64K change. Only the existing
`gemma4-26b-dev:latest` configuration and this isolated branch project's local
profile changed. Installed Flow, user runtime configuration, native provider
profiles, other models and global Ollama server defaults were untouched.

## Exact scopes

- Ollama: `num_ctx` changed from **32,768 to 65,536** on the existing development
  model tag using the supported create API, inheriting the prior model snapshot.
- Related rollback tag: `gemma4-26b-dev-flow-rollback-32k:20261011`, pointing to the
  exact original digest. This references existing blobs rather than duplicating
  or downloading weights.
- Base weight reference, template, system prompt, license, messages, capabilities,
  `model_info` and every other generation parameter were verified unchanged.
  Unrelated model tag digests were verified unchanged.
- New project profile: `.flow/runtime.toml`, previously absent and ignored by the
  repository's existing exclude rule. A reviewable copy is in the evidence folder. It selects only
  the existing Ollama development model at localhost11434.
- Thin SDK support: forward local `max_input_tokens`/`max_output_tokens` and create
  the stock LLMSummarizingCondenser when `condenser_max_tokens` is configured.
  No native permission policy or custom token/compaction controller was added.

The effective SDK context is **65,536**, output allowance **8,192** and summary
threshold **57,344**. Explicit SDK input settings take precedence over the
architecture's 262,144 metadata. The threshold leaves output headroom and uses
stock SDK context management. Unconfigured profiles keep their prior behavior.

## Verification and limits

A short real SDK/Ollama fixture call wrote two artifacts and passed Flow run
verification. Ollama `/api/ps` measured **65,536** loaded context. Persisted SDK
configuration confirmed the input/output/summary settings. Fixture source stayed
unchanged; historical Codex/Claude/32K acceptance evidence was preserved.

Reported model allocation: **17,434,421,492 bytes (16.24 GiB)**, entirely GPU-side.
The prior 32K snapshot was 17,394,638,518 bytes; observed difference is
**39,782,974 bytes (37.94 MiB)**. This is a short-prompt allocation comparison,
not peak memory for a filled 64K prompt. Unified memory means GPU/system usage
must not be added as separate memory pools.

Memory pressure was normal (`1`), system memory free query reported 32%, and swap
occupied 7,841.50 MiB. Larger prompts, actual summary triggering and sustained
coding-load memory/latency were **not** tested. There was no benchmark or long
synthetic prompt. Evidence is in `docs/acceptance/ollama-64k/`.

## Rollback

Restore the exact original model tag via the supported copy API:

```sh
curl http://127.0.0.1:11434/api/copy \
  -H 'Content-Type: application/json' \
  -d '{"source":"gemma4-26b-dev-flow-rollback-32k:20261011","destination":"gemma4-26b-dev:latest"}'
```

Align `.flow/runtime.toml` to `max_input_tokens=32768`,
`max_output_tokens=8192`, `condenser_max_tokens=24576` for an operational 32K
rollback. Remove the new project profile to return to its prior absent-profile
state instead. The added SDK option support can remain; it does not change
unconfigured profiles. A subsequent request loads the restored configuration;
do not stop unrelated model/server processes.

The full original show response, generated Modelfile and tag records are retained
privately under `.venv-openhands/ollama-64k-rollback/`. Public bounded digest and
rollback metadata are in `docs/acceptance/ollama-64k/rollback.json`. No weights,
authentication data or native credentials were copied.

Official API: https://docs.ollama.com/api/create and
https://docs.ollama.com/api/copy .

Validation: 12 focused SDK/workflow tests passed; full repository suite ran
2,135 tests in 412.536 seconds, 68 skipped, zero failures/errors. Diff checks
passed. Real short-call verification passed with the loaded 65,536 context.
