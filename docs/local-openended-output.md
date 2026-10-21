# Open-ended local output

This isolated change supports Ollama's `num_predict=-1`: generate until a stop or the remaining context is exhausted. It does not enlarge context, disable elapsed-time/resource monitoring, or promise an infinite response.

Retained local agents and newly provisioned machine defaults use `output_tokens=-1`. Existing sealed assignments keep their explicit settings; changing an approved assignment requires its ordinary successor process. Positive explicit caps remain supported. A `context_reserve` remains input headroom, not a reserved output allocation when generation is open-ended.

For an Ollama OpenHands runtime profile use `max_output_tokens=-1` alongside the existing `max_input_tokens` and `condenser_max_tokens`. The SDK requires positive output budgets, so Flow omits the sentinel from the SDK constructor and places it in native `extra_body.options.num_predict`. The actual pinned SDK/LiteLLM HTTP path is regression-tested against a loopback receiver. Its context budget is still explicit. A non-Ollama profile cannot use this sentinel.

The v2 device adapter accepts the same runtime-profile sentinel and deliberately omits `GOOSE_MAX_TOKENS` for -1. The shipped Goose validator rejects negative environment values, despite its signed model-config field. Actual shipped-binary loopback tests verify the two exact coding tags produce no `num_predict`, `max_tokens` or `max_completion_tokens`, preserve 32K context and the .875 compaction threshold. Ollama 0.40.6 defaults to NumPredict=-1, and the installed tags contain no model-level output override. Check persistent Goose config for stale GOOSE_MAX_TOKENS before deployment; none was found at the Studio managed or source-bound config paths. Native Codex and Claude settings are untouched.

Knowledge extraction keeps its existing 16,384 context and 180-second HTTP timeout, with generation changed from 1,200 to -1. Its acceptance validation and transaction behavior are unchanged.

Transport/IPC safety bounds remain finite and explicit. Open-ended local-worker responses above the context-derived byte bound fail rather than silently truncate. This is an infrastructure boundary, not a quality result. Framework context exhaustion can still end generation with a length reason.

## Verification

Use the existing pinned MAF interpreter for `test_openended_output.py`, `test_local_worker.py`, `test_local_machine.py`, `test_runner_limits.py` and `test_local_agent.py`. The retained-agent integration test requiring FLOW_MAF_PYTHON was skipped when that variable was absent; frame/session tests passed. Use the pinned OpenHands interpreter with `LITELLM_LOCAL_MODEL_COST_MAP=True OPENHANDS_SUPPRESS_BANNER=1` for `test_runtime_wiring.py` and `test_openended_openhands.py`. The latter starts only a disposable loopback stub and performs no inference. The broader v2 monitoring tests subsequently passed with the existing managed v2 interpreter, which contains LangGraph. Targeted device-environment tests also pass.

## Studio deployment status and MacBook handoff

This branch is not installed. Studio's active source-bound 2.0.0-preview lacks the managed entrypoint. Released v0.52.2 exposes separate knowledge configure/setup and explicit per-work-item coordinator provider/model choices. Its bundled worker recipes remain independent: selecting a Qwen coordinator does not select Qwen for lead-developer. The older device adapter ignores the -1 sentinel. Do not merely edit its legacy profiles and claim activation. The isolated branch now implements explicit per-work implementation profiles; see studio-v0522-model-setup-plan.md. Review, publication and separately authorized migration must precede deployment.

After the fix is deployed in the user's local MacBook session, back up ~/.flow/user/flow.toml and runtime.toml, set `[local_machine].output_tokens=-1` for new retained assignments and each intended Ollama profile's `max_output_tokens=-1`, retaining context, max_context, reserve, condenser and timeout values. Verify unchanged num_ctx. MAF/OpenHands/native enrichment must transmit `num_predict=-1`; shipped Goose must omit all output cap fields and use verified open-ended server/model defaults. A stored Goose cap is a pre-submission conflict, not an accepted fallback. Do not use these settings as a workaround on an unpatched installation. Test enrichment first, and GPT-OSS separately; the 24 GiB M5 Pro currently has warning pressure, about 10 GiB compressor and 6.28 GiB swap with no model loaded. No MacBook operation was performed here.

The additional `test_v2_openended_wire.py` exercises the exact v0.52.2 Goose binary hash e07d4c3771351af306117ee4db069c3c09e4588859e55f6606f28cbd23833318 and executes the actual v2 enrichment function body with only the Coco memo decorator omitted and HTTP receiver mocked. Both pass; no production work item, model inference or corpus writes occur. The v2 files patched here match the official release archive before modifications.
