# Studio model configuration and deployment handoff

Implementation is complete on an isolated branch; the active Studio installation has not been migrated. The patch must be reviewed and published before using the production steps below. It adds explicit worker selection, not an automatic router.

## Supported behavior

`flow --project /path/to/project --work NEW-ID create --request "..." --implementation-profile local-correctness` selects Qwen3.8 for the implementation worker. Use `local-fast` for GPT-OSS. Coordinator `--provider/--model` remain separate and retain their existing defaults. Omit the new option to preserve every existing recipe/provider choice. Explicit native `codex` and `claude` profiles are also accepted.

The selector snapshots profile name, provider/model, loopback endpoint, context, output setting, compaction threshold and installed model digest at creation. The proposal displays it, approval records it, controlled input identity includes it, and dispatch validates it. Later profile-file edits do not retarget existing work. There is no selector on resume; changed selection requires a new work item. The attempt-local lead-developer recipe changes only during implementation. Fresh independent review keeps the original native recipes; checks, deadlines, turn safeguards and knowledge validation remain unchanged. Provider preflight refuses a changed model digest before submission.

The profiles supply model and local transport settings; this feature does not import SDK/native permission policies or establish equivalence with native client isolation. Ollama workers use the framework's existing Goose developer tools and coordinator execution authority. Native client sandbox policies are not rewritten. A separate readiness-only sandbox copy grants the exact selected loopback port for its curl probe; it is not passed to workers. No credentials are acquired or copied by this change.

Goose shares transport settings with in-process local delegates. With a local implementation profile, use the existing native coordinator or the same Ollama model; a different local coordinator is rejected instead of silently sharing incompatible settings. Native client context remains client-owned. Worker context and compaction come from the frozen profile. Sampler/thinking defaults remain Goose/provider-owned and are not claimed identical to the benchmark harness.

## Profile entries after deployment

Back up ~/.flow/user/runtime.toml, then add these selectable profiles without replacing native profiles or rewriting existing context windows:

```toml
[profiles.local-correctness]
kind = "local"
model = "ollama_chat/qwen3.8:27b-q4_K_M"
base_url = "http://127.0.0.1:11434"
max_input_tokens = 32768
max_output_tokens = -1
condenser_max_tokens = 28672

[profiles.local-fast]
kind = "local"
model = "ollama_chat/gpt-oss:20b"
base_url = "http://127.0.0.1:11434"
max_input_tokens = 32768
max_output_tokens = -1
condenser_max_tokens = 28672
```

These new profiles use the coding comparison's 32K allocation; they do not expand an existing window. Existing local profiles whose arbitrary output caps should be removed can change only `max_output_tokens` to -1 while preserving context/condenser fields. Retained-agent `[local_machine].output_tokens=-1` applies only to new assignments after the patch; existing sealed assignments are preserved.

## Safe deployment sequence (not executed)

1. Verify no overlapping active Flow work and preserve source-bound work, launcher/config backups and the entire knowledge corpus. Release the reviewed combined patch through normal gates. Use official bootstrap pinned to that published tag, initially `--knowledge defer --knowledge-model offline` to avoid default qwen3:4b acquisition. Do not install this unpublished branch or substitute the already released v0.52.2, which lacks the selector. Keep the current launcher until reviewed migration is authorized.
2. With the reviewed managed runtime selected, run `flow --version` and `flow doctor`. Configure enrichment separately with `flow knowledge setup --download --model qwen3.5:9b-q4_K_M --ollama http://127.0.0.1:11434`, reusing verified assets where supported. This can trigger processing and needs its normal disk/headroom/readiness checks. It does not pull chat weights or change coding-agent providers. Earlier rolled-back dependency/cache assets exist, but no selected settings/provisioned-runtime file currently exists; do not declare knowledge ready without doctor/status. Keep embeddings/retrieval identity and acceptance validation unchanged. Dates/aliases quality limitations remain unresolved.
3. Add the selectable profiles above. Audit persistent Goose output settings: a stored GOOSE_MAX_TOKENS conflicts with open-ended mode and causes a clear pre-submission refusal, not a hidden cap. For the two tested tags, output omission is verified with shipped Goose; neither model defines num_predict. Other local model canonical defaults need their own wire verification.
4. Create fresh disposable work items with each implementation profile through normal approval. Inspect approval/profile digest, actual worker model and output/context metadata, independent review and independent checks. No production work item was created; disposable acceptance work items are described below. Enrichment readiness and role wiring are separate checks.
5. Rollback is the managed install receipt's `flow rollback`, which refuses conflicting edits and preserves history. Once setup/knowledge/config edits occur, preserve them and reconcile with the receipt rather than forcing rollback. Original launcher/config backups remain under task-3/studio-model-activation-20261021T130905Z. The selector has not changed any production file, so no rollback is currently required.

## Verification and provenance

Official v0.52.2 code archive SHA256: 3a0f33dd6c379eaad5fe324f4f07212f392e3577b105757c1a7b8c45e8a32941. The patched v2 request/knowledge modules match that release before edits. Exact shipped Goose executable: e07d4c3771351af306117ee4db069c3c09e4588859e55f6606f28cbd23833318.

Real shipped-binary loopback tests execute each bound implementation recipe, including developer tools and typed final-output setup. Requests select the exact intended tags, preserve 32K context and omit num_predict/max_tokens/max_completion_tokens. No real model inference, source edits or external sends are performed by those tests. Raw evidence is task-3/released-v0522-inspection/WORKER-WIRE.json. This is a worker request-path test, not a full live LangGraph/native-account acceptance run.

The v2 enrichment payload test verifies Qwen3.5, -1 output, unchanged 16K context and 180-second timeout. It executes the actual extraction function with its memo decorator omitted and HTTP mocked; it does not mutate a corpus. Real SQLite lifecycle tests prove proposal/approval binding and rejection of changed configuration. Existing work defaults, monitoring and provider preflight regressions are also checked.

Ollama 0.40.6 official sources: https://raw.githubusercontent.com/ollama/ollama/v0.40.6/api/types.go has DefaultOptions NumPredict=-1; https://raw.githubusercontent.com/ollama/ollama/v0.40.6/openai/openai.go adds num_predict only when MaxTokens is supplied. Shipped Goose rejects negative GOOSE_MAX_TOKENS; the v2 patch omits that override instead. The separate legacy OpenHands/MAF adapters pass native -1, verified independently.

No MacBook operation occurred. Its pressure baseline requires an enrichment-first fit check and a separate GPT check before choosing laptop defaults.

## Review follow-up: compaction and delegation acceptance

Local implementation profiles now require an explicit positive `condenser_max_tokens` below their context window. An omitted value is rejected before model lookup, even if persistent Goose configuration supplies a threshold. The frozen ratio is always projected into the launch environment; both documented profiles use 28672/32768 = .875. Tests cover later persistent thresholds and conflicting environment values.

Summon inherits its parent's enabled extensions rather than recipe.extensions. Local-profile implementation therefore retains the developer extension on the coordinator session so the local worker receives real edit/test tools. Existing work and native-profile implementation still remove that extension as before. The coordinator is instructed to delegate to lead-developer using the frozen profile and not edit directly or override provider/model. This is an orchestration instruction, not a new security boundary. Review retains the original native bundle and extension behavior.

The new deterministic integration test exercises a real shipped Goose coordinator, summon, selected worker, actual shell edit/test, LangGraph independent check and a simulated native-review boundary for both coding tags. Its fixture sandbox grants workspace/home writes, read-only role definitions and only a local test endpoint. Controller records and graders are outside model write access. Tests also capture the actual production launch command to check that developer retention is opt-in only.

Supplemental live acceptance completed once per coding model, with a deterministic coordinator, real local model generations and developer tool execution, independent tests, and a fresh existing default Claude Opus reviewer. Both fixtures passed all 3 unchanged tests and review. GPT-OSS took 48.5 seconds including review and produced 4 tool-call JSON parsing failures that Goose retried; 9 responses returned usage among 13 generation requests. Qwen3.8 took 126.1 seconds including review, with 7 successful requests and no observed API parse errors. Returned completion-token counts were 625 and 1123 respectively; failed requests omit usage, so GPT's full token cost is unknown. These are acceptance observations on one small task per model, not fresh comparison scores. All actual local requests retained 32K context and omitted output caps. Both models were unloaded.

Raw evidence: task-3/released-v0522-inspection/live-gpt-v1 and live-qwen-v1, including receipts, requests/responses, fixture edits, independent test results, native review, and SQLite lifecycle state. The recorded runs loaded no ancestor instruction documents. The final reusable driver now constructs fixture-only context directly and additionally verifies the shipped binary hash; these fixture-hardening changes were checked with deterministic integration, without repeating live generation.

Production-equivalent reviewer acceptance remains blocked: the private Flow Claude configuration at ~/.flow/v2/state/claude-home reports loggedIn=false. No login or credential transfer was attempted. The existing default Claude session was already authenticated and used only for supplemental fixture review; it was not selected as Flow's production configuration. Real native-coordinator/private-ACP acceptance, integrated knowledge readiness and active migration remain unverified. The two previously recorded baseline test-group failures remain pre-existing and unresolved.
