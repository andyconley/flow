# Handback: repaired gate and live local recovery

**Result:** the bounded repair passed independent review. Flow's prototype dispatch ledger now denies unmetered paid providers, enforces cumulative six/three/two limits, records decisions before dispatch, and denies duplicate request IDs or dispatch claims. A MAF-originated disallowed request produced zero dispatches. One authorized Ollama worker used Flow's test-engineer definition, completed, and checkpointed; a separate process resumed to terminal output without another Flow-recorded dispatch.

Evidence: [validation results](validation-results.md), [receipt](research/receipt.json), [review](review.md), and [reconciliation](reconciliation.md). No paid provider was called in this follow-up. The previous run's Codex cost breach remains in its historical record; this prototype prevents repeating it by denying that path.

**MAF adoption is still pending.** Before production integration, make Flow authorization unavoidable for every Magentic-originated worker request; add failure/unknown and reconciliation states for interruptions during a worker call; prove a commit-bound, independently observed receipt; and assess the roughly 70% machinery reduction. Keep the Flow-native engine freeze in place while these are tested.

No Flow production code, installed dependency, or provider configuration changed. Prototype and evidence live only under this run, with disposable state in `/private/tmp`.
