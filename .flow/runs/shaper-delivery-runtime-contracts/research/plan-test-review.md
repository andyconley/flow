# Planning test review

Deterministic validation must cover canonical contracts, transition concurrency/crashes, owner-generation fencing, unknown-action blocking, projection conformance, selection rationale, zero-send denials, v6 inspection/refusal, CLI output, receipt linkage, and full-suite compatibility.

Use process-level recovery tests and durable `adapter_send_started` evidence. Threads and callback counts alone do not prove the send boundary.

The live acceptance gate runs once after deterministic tests: stock Magentic selects one approved Claude or Codex producer, Flow records why, observes the diff and targeted test, then sends bounded evidence to a distinct Ollama verifier and seals the receipt.

Test-engineer advisory expertise query `27519dcb-f583-4e3a-85b4-79c6f0fa0dd3` returned `no_match`; no advisory content was injected.
