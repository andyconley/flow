# Acceptance criteria

- Magentic routes a proposed worker request through the guarded participant. The disallowed role produces a Flow denial and zero Flow-recorded specialist dispatches.
- The wrapper uses a stable request identity across checkpoint replay and denies a second claim for the same request. The policy counts completed replans toward the two-replan cap.
- A local Ollama worker produces at least one streamed update before an intentional process termination. Flow marks the dispatch `unknown`, with a durable interruption event and no fabricated completion.
- A separate process resumes the pre-dispatch checkpoint; the same request cannot cause another provider invocation. The result states that manual reconciliation is required.
- A receipt checks the Flow ledger, MAF checkpoint, definition and charter digests, and disposable Git state. It labels unobserved physical call counts and semantic output as unverified.
- Independent review approves or rejects the bounded result with explicit remaining production gaps.
