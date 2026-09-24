# Plan: guarded Magentic participants and in-flight interruption

Status: approved scope from Andy's “Proceed” instruction. Run-local research only, using the existing disposable Python environment and local Ollama; no paid dispatch.

1. Carry forward the reviewed Flow SQLite gate, adding an `unknown` state for a dispatch interrupted after a streamed provider update. Unknown work counts against delegation, concurrency, and budget caps; replay cannot dispatch again.
2. Create a guarded participant factory as the only input to a run-local `MagenticBuilder`. The wrapper derives a stable request ID from charter, specialist instance, and MAF request content; calls Flow policy; then claims one dispatch before invoking the provider. Denial or duplicate returns a bounded result to Magentic without invoking a specialist.
3. Use a deterministic Magentic manager to make the next specialist proposal reproducible. Demonstrate a disallowed role receives a Flow denial with zero specialist calls. This tests MAF's actual participant dispatch path, while leaving model-quality evaluation out of scope.
4. For the allowed local worker, persist Magentic's pre-dispatch plan-review checkpoint. Resume it in a child OS process, start streaming from Ollama using the Flow test-engineer definition, persist the first observed update and mark the dispatch `unknown`, then intentionally terminate the process. Resume the same checkpoint in another process; require manual reconciliation, with no second provider dispatch claim.
5. Observe SQLite events, MAF checkpoint, definition/charter digests, and disposable Git state independently. Review the evidence and claim limits, then hand back adoption blockers.

Safety: local-only provider, one specialist stream, no repository edits, no retries of unknown work, no production Flow dependency or CLI/MCP wiring. The prior $10 cap remains, with zero paid calls in this slice.
