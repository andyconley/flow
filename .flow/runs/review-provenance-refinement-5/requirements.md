# Requirements: Review Provenance Refinement Successor

Implement the approved review-only, append-only orchestration amendment mechanism from `review-provenance-refinement-2`, then apply it to complete the blocked MAF review.

Also codify both bootstrap failures discovered during the predecessor runs:

1. `approve-definition` must reject a noncanonical `shaper-intent.json` before sealing its digest.
2. A Delivery-Lead-intended plan must be rejected before implementation unless its manifest and job charter define an executable manager, bounded producer/verifier roster, provider/model bindings, safe target test, and separate worker-worktree requirement.
3. Definition or plan approval must reject a sealed Delivery envelope whose runtime and Magentic limits exceed the protocol-v8 runner bounds.
4. Reproduce and repair the Claude manager turn-count validation failure without weakening unknown-send fencing or automatically replaying uncertain calls.

The successor uses the supported Codex manager/producer path to implement the Claude-path repair. The original Delivery manifest and approved digests remain immutable. The review overlay is limited to verification corrections and appended read-only reviewers. General artifact editing, multiple amendment generations, macOS baseline repair, and MAF redesign remain excluded.
