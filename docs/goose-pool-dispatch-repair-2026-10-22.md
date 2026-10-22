# Goose dispatch binding and readiness repair qualification

Candidate code: `1c73eeb137ba93533079dfbfe78bbc96ea7dd98a`; this supplements the preserved original qualification and independent findings.

Operator-generated source recipes now have SHA-256 and byte-length bindings supplied out of band in the coordinator process environment. Dispatch reads once, verifies against those bindings and parses the same buffer. It rejects in-place provider/model/task/extension modifications, shadow paths and caller route overrides. Preflight receives the same operation source allowlist as dispatch; final review requires only Goose ChatGPT Codex and Claude Opus.

Validation: 368 Python tests pass (3 optional checks skipped), 3 targeted Rust dispatch tests pass, and all 29 patched source files match the pinned base plus recorded patch. The packaged arm64 binary passes provenance, signing and system-linkage checks.

| Fresh case | Evidence |
|---|---|
| dispatch-repair-auto | Real Goose → codex-acp / gpt-5.6-sol → independent frozen tests → fresh private Opus review; reviewed-and-ready |
| dispatch-repair-gpt | Real Goose → ollama / gpt-oss:20b → independent frozen tests → fresh private Opus review; reviewed-and-ready |
| dispatch-repair-claude | Real Goose → claude-acp / sonnet → independent frozen tests → fresh private Opus review; reviewed-and-ready |
| dispatch-repair-qwen-retry | Real Goose → ollama / qwen3.8:27b-q4_K_M → independent frozen tests → fresh private Opus review; reviewed-and-ready |

The four-member pool case autonomously selected Codex. The other three cases restrict the approved pool to one implementation profile and prove callable route coverage, not autonomous selection. All four have real child-session receipts, result consumption, knowledge retrieval and passing unchanged seven-test acceptance. The first Qwen coverage attempt stopped before dispatch with an explicit coordinator `server_is_overloaded` response; its quiescent blocked evidence remains separate, and a fresh fixture subsequently passed.

The previous GPT-OSS generator limitation is not rescored or fixed here. The brief does not explicitly exclude generators; input-container contract coverage is underspecified, and generator support is not established. Seven list-based tests and one small task establish bounded integration evidence, not general model correctness or model ranking.

Production runtime, Goose configuration, installed v0.53.0 binary and all 23 recorded knowledge hashes remain unchanged. Local models are unloaded; approximately 46.64 GiB disk space remains free. No credentials were copied, permissions widened, production settings changed, or release/activation performed.

Fresh independent read-only diff review of `9f42f4bc86852f3f4c433eae92ba6198db04feb9` against `94fa8d710b53f8b097102990ba1cf7efd289166f` found no remaining substantive defects and explicitly closed both prior P1 findings. It verified the full integration diff and preserved evidence; the reviewer did not rerun tests or live workflows. This final report-only update changes no executable code. Raw review: `installed-flow-qualification-20261022/dispatch-repair-independent-review.md`.

[Compact evidence](evidence/goose-pool-dispatch-repair-2026-10-22.json) links source audit, tests, model/session identities, preflight and knowledge observations. Raw local evidence is `installed-flow-qualification-20261022/dispatch-repair-result.json`.
