# Validation plan

- Policy tests cover total delegation, concurrency, replan, specialist allowlist, budget reservation, unmetered Codex denial, and duplicate request IDs.
- A denied MAF-originated request records a Flow denial and zero dispatch events.
- An allowed request invokes one local Ollama worker with a Flow definition and records a result digest.
- Checkpoint after the worker; resume in a second OS process and compare dispatch count before/after.
- Flow-side observer checks fixture Git state and hashes, policy decisions, checkpoint, and worker count; imported model output is labeled as such.
- Independent review checks boundary correctness and claim scope. Mutation check changes one cap in a temporary policy fixture, confirms a covering assertion fails, then restores it.
