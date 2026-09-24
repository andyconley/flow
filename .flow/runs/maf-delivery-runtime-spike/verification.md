# Verification independence

- Producer: `spike-producer` (the coordinator), which wrote prototype scripts, observed provider runs, and produced the bounded result and receipt.
- Verifier: `spike-verifier` (independent quality-reviewer agent), which wrote [review.md](review.md) without running paid providers or editing producer evidence.
- The verifier checked stored JSON/Python syntax, current definition hashes, and the disposable fixture's clean Git HEAD. It requested changes for the cost stop-rule breach and missing dynamic Flow gate. Its verdict is adopted in [reconciliation.md](reconciliation.md).
- Verification is independent for source/result consistency, not for raw provider events. The provider output remains imported evidence; `research/receipt.json` says `provider_result_attested: false`.
