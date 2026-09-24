# Requirements: Magentic dispatch gate and interrupted-call recovery

Approved by Andy's “Proceed” instruction on 2026-09-19, following the reviewed `maf-runtime-control-recovery` handback.

1. Every specialist instance passed to this Magentic workflow must be created through a Flow-owned guarded participant factory. The wrapper must evaluate the cumulative six-delegation, three-concurrent, two-replan, specialist allowlist, and $10 paid-budget envelope before any provider call. Raw participant injection must be rejected by the factory path. The only dispatchable provider in this run is local Ollama; unmetered Codex and Claude remain denied.
2. A Magentic manager must generate a delegation to a disallowed specialist. The Flow wrapper must record denial and return a bounded response to MAF with zero specialist provider calls. Use an actual Magentic orchestration path, not a standalone Flow gate call.
3. A permitted local specialist must begin streaming from Ollama. After observing at least one streamed provider update, intentionally terminate the worker process. Record the dispatch as `unknown` because its outcome cannot be inferred from the absence of a result.
4. A separate process must attempt recovery from a pre-dispatch MAF checkpoint. The Flow ledger must deny duplicate dispatch and require explicit reconciliation; it must not automatically call the provider again. Preserve the original request, definition, charter, and checkpoint identities.
5. A Flow-side observer must verify ledger events, checkpoint identity, the clean disposable Git fixture, and reported streaming evidence. Distinguish Flow-recorded facts from independently measured Ollama server calls and model-output semantics.
6. No production Flow dependency or runtime integration is authorized by this research slice. MAF adoption and the Flow-native engine freeze remain separate decisions.
