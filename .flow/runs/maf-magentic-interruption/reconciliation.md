# Reconciliation

Date: 2026-09-19. Independent [review](review.md): **approve bounded local research result**, not MAF adoption or production guard.

| Claim or finding | Disposition | Evidence and limit |
| --- | --- | --- |
| Actual Magentic participant proposal reached Flow authorization | Accepted for this guarded builder path | `research/magentic_guard_probe.py`, denied Flow ledger and [receipt](research/receipt.json). First attempt used the wrong MAF envelope and did not dispatch; corrected `GroupChatRequestMessage` path produced the accepted result. |
| Disallowed role caused zero specialist dispatch | Accepted | `security-reviewer` request recorded `specialist_denied`; denied ledger has zero dispatch rows. |
| Live local call was interrupted after streamed data | Accepted as wrapper-observed | The marker has a nonempty chunk digest and the intentionally terminated process returned exit 77. No independent Ollama server log was captured. |
| Replay from the same checkpoint did not automatically retry | Accepted as Flow-recorded behavior | Stable request ID stayed `unknown`, one dispatch row remained, `manual_reconciliation_required` was recorded, and terminal recovery output matched the exact checkpoint/request. |
| Request identity works for multiple legitimate calls | Deferred | Fixed `delegation-1` ID is conservative and rejects any later call to the same instance; derive a durable MAF invocation ID bound to Flow run and charter before multi-turn use. |
| All Magentic/Flow construction paths are guarded | Deferred | Only this run-local factory is guarded; production construction must reject raw participants. |
| Magentic replans are Flow-gated | Deferred | Manager disables replanning; unit tests cover only ledger arithmetic. |
| MAF earns adoption as Delivery Lead | Deferred | Multi-turn identity, universal construction boundary, replan authorization, commit-bound receipts, and roughly 70% avoided-machinery estimate remain open. |

The review suggestion to bind the saved recovery summary to its state was implemented after review: it now includes run, checkpoint, and request IDs, and the observer asserts all three. The observer readback passed. The separate exit-code and stream-marker evidence remains a review limit.
