# Acceptance criteria

- Policy tests prove all six/three/two/allowlist/budget limits, deny unmetered Codex, and permit only a provider with a hard cap or a local zero-paid-cost provider.
- A MAF-generated runtime request is inspected by the Flow policy layer before dispatch; an out-of-envelope request is denied with zero provider calls.
- The authorized live Ollama worker runs once using an actual Flow specialist definition. A separate process resumes its post-worker checkpoint and produces terminal output without calling Ollama again.
- Flow's durable event ledger ties request ID, policy decision, worker dispatch, result, and checkpoint. Replaying the request cannot duplicate the dispatch.
- An independent receipt checks the disposable Git fixture and digests, reports the measured provider count, and labels unverified model-output facts.
- Review, validation, and handback state the remaining limits before any MAF adoption decision.
