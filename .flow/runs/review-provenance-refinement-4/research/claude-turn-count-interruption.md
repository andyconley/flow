# Claude Turn-Count Interruption

## Attempt

- ID: `927d88f9b652457fb650fea00eb3a618`
- Runtime: managed MAF activated successfully.
- Contract: protocol v8 envelope and charter validation succeeded.
- Provider activity: the Claude Delivery Lead facts call completed; the following plan call was recorded with unknown outcome.
- Interruption: `reconciliation_required` / `Claude turn count is invalid`.
- Worker actions: none.
- Worktree edits: none.

Flow reported the unknown manager call as unrecoverable and prescribed `abandon-delivery`. The coordinator executed that command with owner generation 1. Flow reaped/gated the recorded process groups, advanced owner generation to 2, and sealed an abandoned receipt with SHA-256 `93f79fb2dadbe7cd674b1554cf9f3ceab789a7fee8bb3c04b781ae9c82faf9ba`.

## Required codification

- Reproduce the Claude multi-turn response shape that triggers invalid turn-count reconciliation.
- Validate or normalize the provider turn count before an otherwise valid manager call becomes an unrecoverable unknown.
- Preserve conservative unknown-send handling; do not automatically replay this call.
- A successor may use the supported Codex manager/producer path to implement and test this Claude-path repair, but that provider change must be sealed as new authority.

